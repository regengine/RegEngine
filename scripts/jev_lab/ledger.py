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
import re
import secrets
import stat
import threading
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import privacy
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


# A question set's label (``baseline``, ``csv-header-mapping.v3``, ``lab-<run>-g<n>-<kind>``) and its
# parent (a digest) as the lab writes them; a hand-edited file is held to the same shapes.
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,47}")
_LAB_LABEL = re.compile(r"lab-[0-9a-f]{12}-g\d{1,3}-(?:" + "|".join(re.escape(kind) for kind in KINDS) + r")")
_DIGEST = re.compile(r"[0-9a-f]{64}")


class LabStateError(RuntimeError):
    """A lab file no longer says what it recorded, or the split moved under a run. The message names the file."""


class EpochChanged(LabStateError):
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

    @property
    def cases_lock(self) -> Path:
        """The lock for ``cases.local.json``: in ``home``, shared by both modes like the file itself."""
        return self.home / ".cases.lock"

    @contextlib.contextmanager
    def _exclusive(self, lock: Path | None = None) -> Iterator[None]:
        """This process's lock plus, where the OS has one, a lock file other processes respect.

        The default lock file lives in this mode's state directory. Writes to
        a file both modes share must pass the lock beside that file.
        """
        with self._lock:
            self.ensure()
            if fcntl is None:
                yield
                return
            with (lock or self.state_dir / ".lock").open("a") as handle:
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
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):  # a hand-edited line that is not a record is skipped like a torn one
                rows.append(row)
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
            with self._exclusive():  # atomic and serialised: a reader never sees a half-written file
                if not path.exists():
                    self._write(qs.to_dict(), path)
        return digest

    def load_set(self, digest: str) -> QuestionSet | None:  # noqa: C901 - one check per field, in order
        """The wording behind ``digest``; ``None`` when there is no such file.

        The file names the wording Jev judged. One that no longer parses, or
        whose wording no longer computes to that digest, is refused with the
        file named: edited or corrupted, it is not that wording any more.
        """
        if not all(ch in "0123456789abcdef" for ch in digest) or len(digest) != 64:
            return None
        path = self.sets_dir / f"{digest}.json"
        try:
            loaded = QuestionSet.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return None
        except (ValueError, KeyError, TypeError, AttributeError):
            raise LabStateError(f"{path} is unreadable: delete it, or restore it from a backup") from None
        if loaded.digest != digest or loaded.kind not in KINDS:
            raise LabStateError(f"{path} does not match its digest: delete it, or restore it from a backup")
        # The label, parent and notes sit outside the digest, so an edited file passes the check above.
        # They are held to the lab's own shapes, and the notes to the privacy guard, before the page,
        # the ledger or the CLI repeats them; a message names the file, never what was in it.
        parent_ok = loaded.parent is None or (isinstance(loaded.parent, str) and _DIGEST.fullmatch(loaded.parent))
        if not _LABEL.fullmatch(loaded.label) or not parent_ok:
            raise LabStateError(
                f"{path} has a label or parent of the wrong shape: delete it, or restore it from a backup"
            )
        # A run's own label is long enough to read as a token; any other label is scanned like a note.
        scanned = (
            {"notes": list(loaded.notes)}
            if _LAB_LABEL.fullmatch(loaded.label)
            else {"label": loaded.label, "notes": list(loaded.notes)}
        )
        found = privacy.findings(scanned)
        if found:
            raise LabStateError(
                f"{path} holds content that must not leave ({'; '.join(found)}): delete it, or restore it"
            )
        return loaded

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
            raise LabStateError(f"{self.split_path} is unreadable: fix it, or delete it to start a new split epoch")
        looks = data.setdefault("looks", {})
        assignment = data.get("assignment")
        counts_ok = isinstance(looks, dict) and all(
            isinstance(n, int) and not isinstance(n, bool) for n in looks.values()
        )
        sides_ok = assignment is None or (
            isinstance(assignment, dict)
            and all(isinstance(k, str) and isinstance(v, str) for k, v in assignment.items())
        )
        if not counts_ok or not sides_ok:  # a value here would otherwise be repeated by a ValueError
            raise LabStateError(f"{self.split_path} is unreadable: fix it, or delete it to start a new split epoch")
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
        winners: dict[str, str] = {}
        for row in rows:
            if row.get("type") != "incumbent" or row.get("kind") not in current:
                continue
            if row.get("baseline_digest") != baseline(row["kind"]).digest or row.get("epoch") != epoch:
                continue
            if trusted is not None and row.get("run_id") not in trusted:
                continue
            winners[row["kind"]] = str(row.get("digest", ""))
        # Only the winning file per kind is read: a superseded one that was edited later never stops the lab.
        for kind, digest in winners.items():
            loaded = self.load_set(digest)
            if loaded is None:
                continue
            if loaded.kind != kind:
                raise LabStateError(
                    f"{self.sets_dir / (digest + '.json')} records {loaded.kind} wording but the ledger names it "
                    f"the {kind} incumbent: delete it, or restore it from a backup"
                )
            current[kind] = loaded
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
        try:
            data = json.loads(self.cases_path.read_text(encoding="utf-8"))
        except ValueError:
            raise LabStateError(f"{self.cases_path} is not JSON: fix it, or delete it") from None
        if not isinstance(data, dict) or not isinstance(data.get("cases", []), list):
            raise LabStateError(f"{self.cases_path} is not a cases file: fix it, or delete it")
        rows = list(data.get("cases") or [])
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
                raise LabStateError(
                    f"{self.cases_path} row {index} is not a case object with a string id: fix or delete it"
                )
        return rows

    def add_case(self, case: Mapping[str, Any]) -> None:
        """Save a labelled row. Relabelling keeps the row's first ``labelled_at``."""
        with self._exclusive(self.cases_lock):
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
