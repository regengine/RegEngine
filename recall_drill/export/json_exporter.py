"""JSON export for drill reports and traceability data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JSONExporter:
    """Export drill reports and traceability data as structured JSON."""

    def export_string(self, data: Any) -> str:
        return json.dumps(data, indent=2, default=str, ensure_ascii=False)

    def export_file(self, data: Any, path: str | Path) -> str:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = self.export_string(data)
        path.write_text(content, encoding="utf-8")
        return str(path)
