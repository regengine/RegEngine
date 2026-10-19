"""The lab's local record: question-set versions, generations and labelled cases. Never committed.

Everything lives under one directory (default ``~/.regengine/jev-lab``,
override with ``JEV_LAB_HOME`` or ``--home``), outside the repository:

* ``ledger.jsonl``: one JSON object per line. ``{"type": "generation", ...}``
  rows record what was proposed, how it scored on each split and why it was
  kept or not; ``{"type": "incumbent", ...}`` rows record each accepted
  question set by digest.
* ``question_sets/<digest>.json``: the wording behind each digest.
* ``split.json``: the current split epoch: the salt that assigns cases to
  the training or held-out split, and how many times each kind's held-out
  split has been used to judge a candidate (capped; see
  :data:`MAX_HOLDOUT_LOOKS`). Accepted wording belongs to the epoch it was
  judged in; rotating the split starts again from production.
* ``cases.local.json``: header rows labelled in the sandbox, in the format of
  ``docs/engineering/examples/jev_eval_cases.json`` (headers and labels only)
  plus ``labelled_at``. A row labelled after the current split epoch began is
  *fresh*: the loop never sees it, and ``confirm`` uses only fresh rows to
  check a rewrite on data no generation was selected on. Rotating the split
  folds fresh rows into the next epoch's split.
* ``jev-cache.jsonl``: answers to identical live requests, keyed by a
  SHA-256 of the request (see :mod:`jev_lab.jev_access`).

Never written: API keys, the page's access token, row values, Claude's
transcript. Each generation row keeps Claude's rationale and the patch.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .questions import KINDS, QuestionSet, baseline

HOME_ENV = "JEV_LAB_HOME"
# Each judgement on the held-out split leaks a little of it into the choice of
# wording. After this many candidate judgements per kind the split is worn and
# must be rotated before more candidates are judged.
MAX_HOLDOUT_LOOKS = 12
DEFAULT_HOME = Path.home() / ".regengine" / "jev-lab"


def default_home() -> Path:
    raw = os.environ.get(HOME_ENV, "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_HOME


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Ledger:
    def __init__(self, home: Path) -> None:
        self.home = home
        self.path = home / "ledger.jsonl"
        self.sets_dir = home / "question_sets"
        self.cases_path = home / "cases.local.json"
        self.cache_path = home / "jev-cache.jsonl"
        self.split_path = home / "split.json"
        self._lock = threading.Lock()

    def ensure(self) -> None:
        self.sets_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.home, 0o700)
        except OSError:
            pass

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
        record = {"at": now_iso(), **row}
        with self._lock:
            self.ensure()
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

    def epoch(self) -> dict[str, Any]:
        """``{"salt", "created", "looks": {kind: n}}``, created on first use."""
        with self._lock:
            if self.split_path.exists():
                try:
                    data = json.loads(self.split_path.read_text(encoding="utf-8"))
                    if isinstance(data.get("salt"), str) and data["salt"]:
                        data.setdefault("looks", {})
                        return data
                except ValueError:
                    pass
            return self._write_epoch()

    def _write_epoch(self) -> dict[str, Any]:
        data = {"salt": secrets.token_hex(8), "created": now_iso(), "looks": {kind: 0 for kind in KINDS}}
        self.ensure()
        self.split_path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
        return data

    def rotate_split(self) -> dict[str, Any]:
        """A new split epoch: new salt, unused held-out split, production wording again."""
        with self._lock:
            data = self._write_epoch()
        self.append({"type": "split_rotated", "epoch": data["salt"]})
        return data

    def record_holdout_look(self, kind: str) -> int:
        with self._lock:
            data = json.loads(self.split_path.read_text(encoding="utf-8"))
            looks = data.setdefault("looks", {})
            looks[kind] = int(looks.get(kind, 0)) + 1
            self.split_path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
            return looks[kind]

    # -- incumbents -------------------------------------------------------------------

    def incumbents(self) -> dict[str, QuestionSet]:
        """The latest accepted question set per kind in this split epoch; production where none was.

        A recorded incumbent built on a production wording that has since
        changed is ignored, so the lab never keeps optimising stale text, and
        one judged on another epoch's held-out split is ignored too.
        """
        current = {kind: baseline(kind) for kind in KINDS}
        epoch = self.epoch()["salt"]
        for row in self.rows():
            if row.get("type") != "incumbent" or row.get("kind") not in current:
                continue
            if row.get("baseline_digest") != baseline(row["kind"]).digest or row.get("epoch") != epoch:
                continue
            loaded = self.load_set(str(row.get("digest", "")))
            if loaded is not None:
                current[row["kind"]] = loaded
        return current

    def record_incumbent(self, qs: QuestionSet, *, generation: int, run_id: str) -> None:
        self.append(
            {
                "type": "incumbent",
                "kind": qs.kind,
                "digest": self.save_set(qs),
                "label": qs.label,
                "generation": generation,
                "run_id": run_id,
                "baseline_digest": baseline(qs.kind).digest,
                "epoch": self.epoch()["salt"],
            }
        )

    def reset(self) -> None:
        """Forget accepted rewrites: the next run starts from production again. History stays."""
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
                    "epoch": self.epoch()["salt"],
                }
            )

    # -- labelled cases -------------------------------------------------------------

    def local_cases(self, *, fresh: bool | None = None) -> list[dict[str, Any]]:
        """Rows labelled here; ``fresh=True`` only those labelled after the epoch began, ``False`` the others."""
        if not self.cases_path.exists():
            return []
        data = json.loads(self.cases_path.read_text(encoding="utf-8"))
        cases = list(data.get("cases") or [])
        if fresh is None:
            return cases
        began = self.epoch()["created"]
        return [case for case in cases if (str(case.get("labelled_at") or "") > began) == fresh]

    def add_case(self, case: Mapping[str, Any]) -> None:
        with self._lock:
            self.ensure()
            cases = [c for c in self.local_cases() if c.get("id") != case["id"]]
            cases.append({**case, "labelled_at": now_iso()})
            document = {
                "version": 1,
                "about": "Header rows labelled in Jev Lab's sandbox. Headers and labels only, never row values.",
                "cases": cases,
            }
            self.cases_path.write_text(json.dumps(document, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
