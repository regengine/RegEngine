"""The lab's local record: question-set versions, generations and labelled cases. Never committed.

Everything lives under one directory (default ``~/.regengine/jev-lab``,
override with ``JEV_LAB_HOME`` or ``--home``), outside the repository. Runs
judged by the offline fake keep their state in ``<home>/fake``, so wording
the fake picked can never become the live incumbent or use up the live
held-out split. Labelled rows are shared: a label is a person's call, not
Jev's.

* ``ledger.jsonl``: one JSON object per line. ``{"type": "generation", ...}``
  rows record what was proposed, how it scored on each split and why it was
  kept or not; ``{"type": "incumbent", ...}`` rows record each accepted
  question set by digest.
* ``question_sets/<digest>.json``: the wording behind each digest.
* ``split.json``: the current split epoch. Its salt and ``assignment`` (case
  id -> training or held-out side) are fixed when the epoch is first used;
  a case that is not in the assignment is *fresh*: the loop never sees it,
  and ``confirm`` checks a rewrite on fresh cases only. ``looks`` counts how
  many candidates each kind's held-out split has judged (capped; see
  :data:`MAX_HOLDOUT_LOOKS`). Accepted wording belongs to the epoch it was
  judged in; rotating the split starts again from production.
* ``cases.local.json`` (in ``<home>``, shared by both modes): header rows
  labelled in the sandbox, in the format of
  ``docs/engineering/examples/jev_eval_cases.json`` (headers and labels only)
  plus the time each row was first labelled.
* ``jev-cache.jsonl``: answers to identical live requests, keyed by a
  SHA-256 of the request (see :mod:`jev_lab.jev_access`).

Never written: API keys, the page's access token, row values, Claude's
transcript. Each generation row keeps Claude's rationale and the patch.
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import stat
import threading
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .questions import KINDS, QuestionSet, baseline

try:  # POSIX: serialise split.json updates across processes (a CLI run next to the page).
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

HOME_ENV = "JEV_LAB_HOME"
# Each judgement on the held-out split leaks a little of it into the choice of
# wording. After this many candidate judgements per kind the split is worn and
# must be rotated before more candidates are judged.
MAX_HOLDOUT_LOOKS = 12
DEFAULT_HOME = Path.home() / ".regengine" / "jev-lab"
LIVE = "live"
FAKE = "fake"


class EpochChanged(RuntimeError):
    """The split was rotated while a run was using it: the run must stop."""


def _judged_by_fake(row: Mapping[str, Any]) -> bool:
    jev = row.get("jev")
    return row.get("mode") == FAKE or (isinstance(jev, Mapping) and jev.get("mode") == FAKE)


def _judged_live(row: Mapping[str, Any]) -> bool:
    jev = row.get("jev")
    return row.get("mode") == LIVE or (isinstance(jev, Mapping) and jev.get("mode") == LIVE)


def default_home() -> Path:
    raw = os.environ.get(HOME_ENV, "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_HOME


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Ledger:
    def __init__(self, home: Path, *, mode: str = LIVE) -> None:
        if mode not in (LIVE, FAKE):
            raise ValueError(f"unknown mode {mode!r}")
        self.home = home
        self.mode = mode
        self.state_dir = home if mode == LIVE else home / FAKE
        self.path = self.state_dir / "ledger.jsonl"
        self.sets_dir = self.state_dir / "question_sets"
        self.cache_path = self.state_dir / "jev-cache.jsonl"
        self.split_path = self.state_dir / "split.json"
        self.cases_path = home / "cases.local.json"
        self._lock = threading.Lock()

    def ensure(self) -> None:
        self.sets_dir.mkdir(parents=True, exist_ok=True)
        for directory in {self.home, self.state_dir}:
            try:
                os.chmod(directory, stat.S_IRWXU)  # owner only: the ledger names labelled headers
            except OSError:
                pass

    @contextlib.contextmanager
    def _exclusive(self) -> Iterator[None]:
        """This process's lock plus, where the OS has one, a lock file other processes respect."""
        with self._lock:
            self.ensure()
            if fcntl is None:
                yield
                return
            with (self.state_dir / ".lock").open("a") as handle:
                fcntl.flock(handle, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle, fcntl.LOCK_UN)

    # -- rows ------------------------------------------------------------------

    def rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
        return rows

    def append(self, row: Mapping[str, Any]) -> dict[str, Any]:
        record = {"at": now_iso(), "mode": self.mode, **row}
        with self._exclusive():
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def generations(self) -> list[dict[str, Any]]:
        return [row for row in self.rows() if row.get("type") == "generation"]

    # -- question sets -------------------------------------------------------------

    def save_set(self, qs: QuestionSet) -> str:
        digest = qs.digest
        path = self.sets_dir / f"{digest}.json"
        if not path.exists():
            self.ensure()
            path.write_text(json.dumps(qs.to_dict(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        return digest

    def load_set(self, digest: str) -> QuestionSet | None:
        if not all(ch in "0123456789abcdef" for ch in digest) or len(digest) != 64:
            return None
        path = self.sets_dir / f"{digest}.json"
        if not path.exists():
            return None
        return QuestionSet.from_dict(json.loads(path.read_text(encoding="utf-8")))

    # -- split epoch -----------------------------------------------------------------

    def _read_epoch(self) -> dict[str, Any] | None:
        """The stored epoch, ``None`` when there is none yet; an unreadable file is an error, never a new epoch."""
        if not self.split_path.exists():
            return None
        try:
            data = json.loads(self.split_path.read_text(encoding="utf-8"))
        except ValueError:
            data = None
        if not isinstance(data, dict) or not isinstance(data.get("salt"), str) or not data["salt"]:
            raise RuntimeError(f"{self.split_path} is unreadable: fix it, or delete it to start a new split epoch")
        data.setdefault("looks", {})
        return data

    def _write(self, data: Mapping[str, Any], path: Path | None = None) -> None:
        """Write JSON atomically: a reader sees the old file or the new one, never half of one."""
        target = path or self.split_path
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(target)

    def _new_epoch(self) -> dict[str, Any]:
        data = {"salt": secrets.token_hex(8), "created": now_iso(), "looks": {kind: 0 for kind in KINDS}}
        self._write(data)
        return data

    def epoch(self) -> dict[str, Any]:
        """``{"salt", "created", "looks", "assignment"?}``, created on first use."""
        with self._exclusive():
            return self._read_epoch() or self._new_epoch()

    def assign(self, split: Mapping[str, str], *, salt: str) -> dict[str, str]:
        """Fix the epoch's case -> side assignment the first time it is used; return the fixed one."""
        with self._exclusive():
            data = self._read_epoch()
            if data is None or data["salt"] != salt:
                raise EpochChanged("the split was rotated")
            if not data.get("assignment"):
                data["assignment"] = dict(split)
                self._write(data)
            return dict(data["assignment"])

    def rotate_split(self) -> dict[str, Any]:
        """A new split epoch: new salt, unused held-out split, production wording again."""
        with self._exclusive():
            data = self._new_epoch()
        self.append({"type": "split_rotated", "epoch": data["salt"]})
        return data

    def record_holdout_look(self, kind: str, *, salt: str) -> int:
        with self._exclusive():
            data = self._read_epoch()
            if data is None or data["salt"] != salt:
                raise EpochChanged("the split was rotated")
            looks = data.setdefault("looks", {})
            looks[kind] = int(looks.get(kind, 0)) + 1
            self._write(data)
            return looks[kind]

    # -- incumbents -------------------------------------------------------------------

    def incumbents(self) -> dict[str, QuestionSet]:
        """The latest accepted question set per kind in this split epoch; production where none was.

        A recorded incumbent built on a production wording that has since
        changed is ignored, so the lab never keeps optimising stale text, and
        one judged on another epoch's held-out split is ignored too. A live
        ledger accepts only wording live Jev judged (see :meth:`live_runs`):
        a home written before fake runs moved to ``<home>/fake`` can hold
        rows the offline fake picked.
        """
        current = {kind: baseline(kind) for kind in KINDS}
        epoch = self.epoch()["salt"]
        rows = self.rows()
        trusted = self.live_runs(rows) if self.mode == LIVE else None
        for row in rows:
            if row.get("type") != "incumbent" or row.get("kind") not in current:
                continue
            if row.get("baseline_digest") != baseline(row["kind"]).digest or row.get("epoch") != epoch:
                continue
            if trusted is not None and row.get("run_id") not in trusted:
                continue
            loaded = self.load_set(str(row.get("digest", "")))
            if loaded is not None:
                current[row["kind"]] = loaded
        return current

    def live_runs(self, rows: list[dict[str, Any]] | None = None) -> set[str]:
        """Runs with positive evidence that live Jev judged them, and none that the fake did.

        Evidence is a row of the run stamped ``mode: live`` or carrying the
        live decider's stats (``jev.mode: live``). ``reset`` counts: it only
        ever restores production wording. A run any row of which says the
        fake judged it is never trusted, and neither is one with no evidence
        at all (an older lab's fake run cut off before it wrote one).
        """
        rows = self.rows() if rows is None else rows
        live = {"reset"}
        fake = set()
        for row in rows:
            run_id = row.get("run_id")
            if not run_id:
                continue
            if _judged_by_fake(row):
                fake.add(run_id)
            elif _judged_live(row):
                live.add(run_id)
        return live - fake

    def judged_by_fake(self, digest: str) -> bool:
        """True unless this ledger shows live Jev judged the wording (production wording always counts)."""
        if self.mode == FAKE:
            return True
        if digest in {baseline(kind).digest for kind in KINDS}:
            return False
        rows = self.rows()
        trusted = self.live_runs(rows)
        for row in rows:
            named = row.get("digest") == digest or digest in (row.get("candidates") or {}).values()
            if named and row.get("run_id") in trusted:
                return False
        return True

    def record_incumbent(self, qs: QuestionSet, *, generation: int, run_id: str, salt: str) -> None:
        if self.epoch()["salt"] != salt:
            raise EpochChanged("the split was rotated")
        self.append(
            {
                "type": "incumbent",
                "kind": qs.kind,
                "digest": self.save_set(qs),
                "label": qs.label,
                "generation": generation,
                "run_id": run_id,
                "baseline_digest": baseline(qs.kind).digest,
                "epoch": salt,
            }
        )

    def reset(self) -> None:
        """Forget accepted rewrites: the next run starts from production again. History stays."""
        salt = self.epoch()["salt"]
        self.append({"type": "reset"})
        for kind in KINDS:
            base = baseline(kind)
            self.append(
                {
                    "type": "incumbent",
                    "kind": kind,
                    "digest": self.save_set(base),
                    "label": base.label,
                    "generation": 0,
                    "run_id": "reset",
                    "baseline_digest": base.digest,
                    "epoch": salt,
                }
            )

    # -- labelled cases -------------------------------------------------------------

    def local_cases(self) -> list[dict[str, Any]]:
        if not self.cases_path.exists():
            return []
        data = json.loads(self.cases_path.read_text(encoding="utf-8"))
        return list(data.get("cases") or [])

    def add_case(self, case: Mapping[str, Any]) -> None:
        """Save a labelled row. Relabelling keeps the row's first ``labelled_at``."""
        with self._exclusive():
            existing = {c.get("id"): c for c in self.local_cases()}
            first = (existing.get(case["id"]) or {}).get("labelled_at") or now_iso()
            cases = [c for c in existing.values() if c.get("id") != case["id"]]
            cases.append({**case, "labelled_at": first})
            document = {
                "version": 1,
                "about": "Header rows labelled in Jev Lab's sandbox. Headers and labels only, never row values.",
                "cases": cases,
            }
            self._write(document, self.cases_path)
