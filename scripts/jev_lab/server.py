"""Jev Lab's local web server: the sandbox, the loop controls and the event stream behind the page.

Local-only by construction:

* It binds ``127.0.0.1`` (the CLI has no host option).
* Every ``/api`` request needs ``Authorization: Bearer <token>``. The token is
  random per process and reaches the page in the URL fragment, which the
  browser never sends to a server; the page keeps it in ``sessionStorage``.
* The ``Host`` header must name this server (DNS-rebinding defence) and a
  cross-site ``Origin`` or ``Sec-Fetch-Site`` is refused, so another web page
  cannot spend your Jev or Claude credits. No CORS headers are ever sent.
* A strict Content-Security-Policy: the page loads only its own script and
  stylesheet and talks only to this server.

Everything sent to Jev passes :func:`jev_lab.privacy.check` first.
"""

from __future__ import annotations

import asyncio
import collections
import contextlib
import hashlib
import json
import re
import secrets
import threading
from collections.abc import AsyncIterator, Callable, Mapping
from pathlib import Path
from typing import Any

from app import csv_templates as route
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from shared.jev import JevUnavailable, header_mapping as hm

from . import load_script, privacy
from .jev_access import LabDecider
from .ledger import MAX_HOLDOUT_LOOKS, LabStateError, Ledger
from .loop import LoopConfig, confirm, epoch_split, every_case, header_key, run_estimate, run_loop, validate_cases
from .proposer import BACKENDS, build_proposer
from .questions import FILE_CTE, HEADER_MAPPING, KINDS, baseline, changed_options
from .scoring import ask_headers

jev_ask = load_script("jev_ask")
jev_eval = load_script("jev_eval")

STATIC = Path(__file__).resolve().parent / "static"
STATIC_FILES = {"lab.js": "text/javascript", "lab.css": "text/css"}
MAX_QUESTIONS = 20
MAX_REQUEST_JSON = 60_000
MAX_HEADERS = 200
MAX_GENERATIONS = 25
MAX_BODY_BYTES = 256_000
# Ask Jev events outlive a run's events in the replay buffer, so a reconnecting page redraws every mote.
SESSION_EVENTS = frozenset({"sandbox", "feedback"})
MAX_SESSION_EVENTS = 800
STREAM_POLL_SECONDS = 1.0  # how often an idle event stream checks for shutdown
KEEP_ALIVE_SECONDS = 15.0
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-Frame-Options": "DENY",
}


class EventHub:
    """Fan-out of loop events to every open page; keeps the current run's events for late joiners."""

    def __init__(self, keep: int = 4000) -> None:
        self._lock = threading.Lock()
        self._buffer: collections.deque[dict[str, Any]] = collections.deque(maxlen=keep)
        self._subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue[dict[str, Any]]]] = set()
        self._seq = 0

    def publish(self, event: str, data: Mapping[str, Any]) -> None:
        with self._lock:
            self._seq += 1
            item = {"seq": self._seq, "event": event, "data": json.loads(json.dumps(data, default=str))}
            if event == "run_started":
                # A new run replaces the last one's events; Ask Jev's motes belong to the session, not a run.
                kept = [old for old in self._buffer if old["event"] in SESSION_EVENTS][-MAX_SESSION_EVENTS:]
                self._buffer.clear()
                self._buffer.extend(kept)
            self._buffer.append(item)
            subscribers = list(self._subscribers)
        for loop, queue in subscribers:
            loop.call_soon_threadsafe(_offer, queue, item)

    def subscribe(self) -> tuple[asyncio.Queue[dict[str, Any]], list[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=20_000)
        with self._lock:
            backlog = list(self._buffer)
            self._subscribers.add((asyncio.get_running_loop(), queue))
        return queue, backlog

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._subscribers = {entry for entry in self._subscribers if entry[1] is not queue}


def _offer(queue: asyncio.Queue[dict[str, Any]], item: dict[str, Any]) -> None:
    try:
        queue.put_nowait(item)
    except asyncio.QueueFull:
        pass


class Lab:
    """The state one server process holds."""

    def __init__(
        self,
        *,
        decider: LabDecider,
        ledger: Ledger,
        proposer_backend: str,
        proposer_model: str,
        port: int,
        token: str | None = None,
        extra_hosts: tuple[str, ...] = (),
    ) -> None:
        self.decider = decider
        self.ledger = ledger
        self.proposer_backend = proposer_backend
        self.proposer_model = proposer_model
        self.port = port
        self.token = token or secrets.token_urlsafe(32)
        self.hub = EventHub()
        self.hosts = {f"127.0.0.1:{port}", f"localhost:{port}", *extra_hosts}
        self.origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
        self._loop_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._starting = threading.Lock()
        self.last_summary: dict[str, Any] | None = None
        self.loop_error: str | None = None
        # Set by the CLI to uvicorn's exit flag: an open event stream must not hold Ctrl-C hostage.
        self.shutting_down: Callable[[], bool] = lambda: False

    @property
    def running(self) -> bool:
        return self._loop_thread is not None and self._loop_thread.is_alive()

    def start_loop(self, config: LoopConfig, backend: str) -> None:
        with self._starting:  # two clicks or two tabs: one run
            if self.running:
                raise RuntimeError("a run is already in progress")
            every_case(self.ledger)  # a tainted or broken cases file is refused here, before a run starts
            self._start(config, build_proposer(backend, model=self.proposer_model))

    def _start(self, config: LoopConfig, proposer: Any) -> None:
        self._stop = threading.Event()
        self.loop_error = None

        def target() -> None:
            try:
                self.last_summary = run_loop(
                    ledger=self.ledger,
                    decider=self.decider,
                    proposer=proposer,
                    config=config,
                    emit=self.hub.publish,
                    stop=self._stop,
                )
            except Exception as exc:  # noqa: BLE001 - surfaced on the page, never swallowed silently
                self.loop_error = f"{type(exc).__name__}: {exc}"
                self.hub.publish("run_failed", {"error": self.loop_error})

        self._loop_thread = threading.Thread(target=target, name="jev-lab-loop", daemon=True)
        self._loop_thread.start()

    def stop_loop(self) -> None:
        self._stop.set()

    def status(self) -> dict[str, Any]:
        _, split, every = epoch_split(self.ledger)
        epoch = self.ledger.epoch()
        return {
            "mode": self.decider.mode,
            "epoch": {"created": epoch.get("created"), "looks": dict(epoch.get("looks", {})), "cap": MAX_HOLDOUT_LOOKS},
            "jev": {**self.decider.settings.public_summary(), **self.decider.stats()},
            "auto_apply_confidence": self.decider.settings.auto_apply_confidence,
            "review_confidence": self.decider.settings.review_confidence,
            "proposer": {"backend": self.proposer_backend, "model": self.proposer_model, "backends": list(BACKENDS)},
            "loop": {"running": self.running, "error": self.loop_error, "last": self.last_summary},
            "cases": {
                "total": sum(1 for case in every if case.id in split),
                "local": len(self.ledger.local_cases()),
                "fresh": sum(1 for case in every if case.id not in split),
            },
            "estimate": run_estimate(every, split),
            "incumbents": {
                kind: {"label": qs.label, "digest": qs.digest} for kind, qs in self.ledger.incumbents().items()
            },
            "vocabulary": {kind: list(baseline(kind).criteria) for kind in (HEADER_MAPPING, FILE_CTE)},
            "home": str(self.ledger.home),
        }


def answer_confidence(answer: Mapping[str, Any]) -> float | None:
    """How sure Jev was of the answer it gave: a confident "no" is as sure as a confident "yes"."""
    if answer.get("type") == "noul" and isinstance(answer.get("probability_yes"), (int, float)):
        p = float(answer["probability_yes"])
        return max(p, 1.0 - p)
    confidence = answer.get("confidence")
    return float(confidence) if isinstance(confidence, (int, float)) else None


def _refuse(reasons: list[str]) -> JSONResponse:
    return JSONResponse(status_code=422, content={"refused": reasons})


def _validated_questions(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict) or not raw:
        raise HTTPException(400, "questions must be a non-empty object of question objects")
    if len(raw) > MAX_QUESTIONS:
        raise HTTPException(400, f"at most {MAX_QUESTIONS} questions per request")
    for question_id, question in raw.items():
        if not isinstance(question, dict) or question.get("type") not in ("choice", "noul", "score"):
            raise HTTPException(400, f"question {question_id!r} needs a type of choice, noul or score")
        if not question.get("instructions"):
            raise HTTPException(400, f"question {question_id!r} needs instructions")
        if not isinstance(question["instructions"], (str, dict)):
            raise HTTPException(400, f"question {question_id!r}: instructions must be text or an object")
        criteria = question.get("criteria")
        if question["type"] == "choice" and (
            not isinstance(criteria, (dict, list)) or len(criteria) < 2 or not all(isinstance(k, str) for k in criteria)
        ):
            raise HTTPException(400, f"choice question {question_id!r} needs at least two options")
        if question["type"] == "score" and (not isinstance(criteria, list) or not 2 <= len(criteria) <= 10):
            raise HTTPException(400, f"score question {question_id!r} needs 2 to 10 levels")
    return raw


def create_app(lab: Lab) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        lab.stop_loop()  # a run stops with the server, never keeps spending Jev or Claude requests

    app = FastAPI(title="Jev Lab", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.exception_handler(privacy.Refused)
    async def refused(_request: Request, exc: privacy.Refused) -> JSONResponse:
        # A labelled row in cases.local.json that must not leave: nothing was sent, the reasons name no content.
        return _refuse(exc.reasons)

    @app.exception_handler(LabStateError)
    async def unusable_state(_request: Request, exc: LabStateError) -> JSONResponse:
        # A lab file that no longer says what it recorded (split.json, a question set, cases.local.json): say which.
        return JSONResponse(status_code=500, content={"error": str(exc)})

    @app.middleware("http")
    async def guard(request: Request, call_next: Any) -> Response:
        length = request.headers.get("content-length", "0")
        if request.headers.get("host", "") not in lab.hosts:
            response: Response = JSONResponse(status_code=403, content={"error": "unexpected Host header"})
        elif not length.isdigit() or int(length) > MAX_BODY_BYTES:
            response = JSONResponse(status_code=413, content={"error": f"request body over {MAX_BODY_BYTES} bytes"})
        elif request.url.path.startswith("/api/") and not _same_origin(request, lab, post=request.method == "POST"):
            response = JSONResponse(status_code=403, content={"error": "cross-origin request refused"})
        elif request.url.path.startswith("/api/") and not _authorized(request, lab):
            response = JSONResponse(status_code=401, content={"error": "missing or wrong access token"})
        else:
            response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        else:  # the page and its script revalidate on every load, so an upgrade never pairs old HTML with new JS
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html", media_type="text/html")

    @app.get("/static/{name}")
    def static(name: str) -> FileResponse:
        if name not in STATIC_FILES:
            raise HTTPException(404)
        return FileResponse(STATIC / name, media_type=STATIC_FILES[name])

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        return lab.status()

    @app.post("/api/ask")
    def ask(body: dict[str, Any] = Body(...)) -> Any:
        questions = _validated_questions(body.get("questions"))
        state = body.get("state")
        if len(json.dumps({"state": state, "questions": questions})) > MAX_REQUEST_JSON:
            raise HTTPException(413, f"state and questions are over {MAX_REQUEST_JSON} characters")
        reasons = privacy.findings({"state": state, "questions": questions})
        if reasons:
            return _refuse(reasons)
        try:
            answers = lab.decider.ask(state, questions, purpose="jev_lab_sandbox", questions_version="adhoc")
        except JevUnavailable as exc:
            return JSONResponse(status_code=503, content={"unavailable": exc.reason})
        report = jev_ask.answers_report(answers, questions)
        # The page's own handle on this ask: Jev's request id can be absent, and must not collide.
        ask_id = secrets.token_hex(6)
        for question_id, answer in report["answers"].items():
            lab.hub.publish(
                "sandbox",
                {"ask_id": ask_id, "question_id": question_id, "confidence": answer_confidence(answer)},
            )
        return {**report, "ask_id": ask_id, "text": jev_ask.render_text(report), "mode": lab.decider.mode}

    @app.post("/api/adhoc-feedback")
    def adhoc_feedback(body: dict[str, Any] = Body(...)) -> Any:
        verdict = body.get("verdict")
        if verdict not in ("right", "wrong"):
            raise HTTPException(400, "verdict must be right or wrong")
        confidence = body.get("confidence")
        row = {
            "type": "adhoc_feedback",
            "request_id": str(body.get("request_id") or "")[:80] or None,
            "question_id": str(body.get("question_id") or "")[:64],
            "question_type": body.get("type") if body.get("type") in ("choice", "noul", "score") else None,
            "confidence": float(confidence) if isinstance(confidence, (int, float)) else None,
            "verdict": verdict,
            "mode": lab.decider.mode,
        }
        lab.ledger.append(row)
        ask_id = str(body.get("ask_id") or "")[:32]
        lab.hub.publish("feedback", {"ask_id": ask_id, "question_id": row["question_id"], "verdict": verdict})
        return {"saved": True}

    @app.post("/api/headers")
    def headers(body: dict[str, Any] = Body(...)) -> Any:
        row = body.get("headers")
        if not isinstance(row, list) or not row or not all(isinstance(h, str) for h in row):
            raise HTTPException(400, "headers must be a non-empty list of strings")
        if len(row) > MAX_HEADERS:
            raise HTTPException(400, f"at most {MAX_HEADERS} headers")
        reasons = privacy.findings(row) + privacy.data_row_findings(row)
        if reasons:
            return _refuse(reasons)
        wording = body.get("wording", "incumbent")
        if wording not in ("incumbent", "production"):
            raise HTTPException(400, "wording must be incumbent or production")
        sets = lab.ledger.incumbents() if wording == "incumbent" else {kind: baseline(kind) for kind in KINDS}
        try:
            result = ask_headers(row, sets, lab.decider)
        except ValueError as exc:
            raise HTTPException(400, f"refused, production would not send this row: {exc}") from None
        except JevUnavailable as exc:
            return JSONResponse(status_code=503, content={"unavailable": exc.reason})
        return {**result, "mode": lab.decider.mode}

    @app.post("/api/labels")
    def labels(body: dict[str, Any] = Body(...)) -> Any:
        row = body.get("headers")
        if not isinstance(row, list) or not row or not all(isinstance(h, str) and h.strip() for h in row):
            raise HTTPException(400, "headers must be a non-empty list of non-empty strings")
        if hm.malformed_header_reason(row):
            raise HTTPException(400, "refused: a header has a line break or is too long")
        mappings = body.get("mappings") or {}
        cte_label = body.get("cte")
        reasons = privacy.findings({"headers": row, "cte": cte_label, "mappings": mappings})
        reasons += privacy.data_row_findings(row) + privacy.value_findings({"cte": cte_label, "mappings": mappings})
        if reasons:
            return _refuse(reasons)
        case_id = "local-" + hashlib.sha256("\x1f".join(row).encode("utf-8")).hexdigest()[:12]
        case = {"id": case_id, "headers": [h.strip() for h in row], "cte": cte_label or None, "mappings": mappings}
        try:
            parsed = validate_cases(lab.ledger, [case])
        except jev_eval._UsageError as exc:
            raise HTTPException(400, re.sub(r"^\S+\.json case ", "case ", str(exc))) from None
        twin = next(
            (
                other.id
                for other in every_case(lab.ledger)
                if other.id != case_id and header_key(other.headers) == header_key(row)
            ),
            None,
        )
        if twin is not None:
            raise HTTPException(400, f"this header row is already labelled as case {twin}")
        already_read = jev_eval.recognized_labels(parsed)
        if already_read:
            raise HTTPException(400, "the parser already reads " + ", ".join(already_read) + "; it is never asked")
        asked = set(hm.unrecognized_headers(row, route._RECOGNIZED_COLUMNS)[: hm.MAX_COLUMNS_PER_UPLOAD])
        beyond = [header for header in mappings if header.strip() not in asked]
        if beyond:
            raise HTTPException(
                400,
                f"production asks about the first {hm.MAX_COLUMNS_PER_UPLOAD} unrecognised columns only; "
                f"{len(beyond)} labelled column(s) are beyond that",
            )
        lab.ledger.add_case(case)
        return {"id": case_id, "local_cases": len(lab.ledger.local_cases())}

    @app.post("/api/loop/start")
    def start(body: dict[str, Any] = Body(default={})) -> Any:
        backend = body.get("proposer") or lab.proposer_backend
        if backend not in BACKENDS:
            raise HTTPException(400, f"proposer must be one of {', '.join(BACKENDS)}")
        raw_generations = body.get("generations")
        raw_margin = body.get("margin")
        try:
            generations = 5 if raw_generations is None else int(raw_generations)
        except (TypeError, ValueError):
            generations = -1
        if not 0 <= generations <= MAX_GENERATIONS:
            raise HTTPException(400, f"generations must be 0 (score only) to {MAX_GENERATIONS}")
        try:
            margin = 0.01 if raw_margin is None else float(raw_margin)
        except (TypeError, ValueError):
            margin = -1.0
        if not 0.0 <= margin <= 0.5:
            raise HTTPException(400, "margin must be between 0 and 0.5")
        try:
            lab.start_loop(LoopConfig(generations=generations, margin=margin), backend)
        except LabStateError:
            raise  # a lab file no longer says what it recorded: the app's handler names it
        except RuntimeError as exc:
            return JSONResponse(status_code=409, content={"error": str(exc)})
        return {"started": True, "proposer": backend, "generations": generations, "margin": margin}

    @app.post("/api/loop/stop")
    def stop() -> dict[str, Any]:
        lab.stop_loop()
        return {"stopping": lab.running}

    @app.get("/api/ledger")
    def ledger() -> dict[str, Any]:
        rows = lab.ledger.rows()
        return {"rows": rows[-400:], "incumbents": lab.status()["incumbents"]}

    @app.get("/api/question-sets/{digest}")
    def question_set(digest: str) -> Any:
        found = lab.ledger.load_set(digest)
        if found is None:
            raise HTTPException(404, "no question set with that digest")
        return found.to_dict()

    @app.get("/api/question-sets/{digest}/diff")
    def question_set_diff(digest: str) -> Any:
        found = lab.ledger.load_set(digest)
        if found is None:
            raise HTTPException(404, "no question set with that digest")
        base = baseline(found.kind)
        changes = []
        for name in changed_options(base, found):
            if name in ("task", "guidance"):
                changes.append({"name": name, "production": getattr(base, name), "candidate": getattr(found, name)})
            else:
                changes.append(
                    {"name": name, "production": base.criteria.get(name), "candidate": found.criteria.get(name)}
                )
        return {"kind": found.kind, "label": found.label, "digest": digest, "baseline": base.label, "changes": changes}

    @app.post("/api/ledger/reset")
    def reset() -> Any:
        if lab.running:
            return JSONResponse(status_code=409, content={"error": "stop the run first"})
        lab.ledger.reset()
        return {"reset": True}

    @app.post("/api/confirm")
    def confirm_endpoint(body: dict[str, Any] = Body(...)) -> Any:
        digest = str(body.get("digest") or "")
        candidate = lab.ledger.load_set(digest)
        if candidate is None:
            raise HTTPException(404, "no question set with that digest")
        if lab.running:
            return JSONResponse(status_code=409, content={"error": "stop the run first"})
        try:
            return confirm(lab.ledger, lab.decider, candidate)
        except JevUnavailable as exc:
            return JSONResponse(status_code=503, content={"unavailable": exc.reason})

    @app.post("/api/ledger/rotate")
    def rotate() -> Any:
        if lab.running:
            return JSONResponse(status_code=409, content={"error": "stop the run first"})
        lab.ledger.rotate_split()
        return {"rotated": True}

    @app.get("/api/events")
    async def events(request: Request) -> StreamingResponse:
        queue, backlog = lab.hub.subscribe()

        async def stream() -> AsyncIterator[bytes]:
            try:
                # replay_until: events up to this id are history the page redraws but does not announce.
                replay_until = backlog[-1]["seq"] if backlog else 0
                try:
                    hello: dict[str, Any] = {"status": lab.status()}
                except privacy.Refused as exc:  # worded as the page words a refused /api/status
                    hello = {"status": None, "error": "Refused, nothing was sent: " + "; ".join(exc.reasons)}
                except LabStateError as exc:
                    hello = {"status": None, "error": str(exc)}
                yield _sse("hello", {**hello, "backlog": len(backlog), "replay_until": replay_until}, 0)
                for item in backlog:
                    yield _sse(item["event"], item["data"], item["seq"])
                idle = 0.0
                while not lab.shutting_down() and not await request.is_disconnected():
                    try:
                        item = await asyncio.wait_for(queue.get(), timeout=STREAM_POLL_SECONDS)
                    except asyncio.TimeoutError:
                        idle += STREAM_POLL_SECONDS
                        if idle >= KEEP_ALIVE_SECONDS:
                            idle = 0.0
                            yield b": keep-alive\n\n"
                        continue
                    idle = 0.0
                    yield _sse(item["event"], item["data"], item["seq"])
            finally:
                lab.hub.unsubscribe(queue)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})

    return app


def _sse(event: str, data: Any, seq: int) -> bytes:
    return f"id: {seq}\nevent: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode("utf-8")


def _same_origin(request: Request, lab: Lab, *, post: bool) -> bool:
    """The page's own origin. A POST must say so (browsers always send ``Origin`` on one)."""
    origin = request.headers.get("origin")
    if (origin is None and post) or (origin is not None and origin not in lab.origins):
        return False
    site = request.headers.get("sec-fetch-site")
    return site in (None, "same-origin", "none")


def _authorized(request: Request, lab: Lab) -> bool:
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    return scheme.lower() == "bearer" and secrets.compare_digest(value.strip().encode(), lab.token.encode())
