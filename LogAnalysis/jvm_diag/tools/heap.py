from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from jvm_diag.config import Settings
from jvm_diag.tools.mat_parse import parse_mat_pages


@tool
def analyze_heap_dump(heap_file: str) -> dict:
    """Analyze a .hprof / .heapdump file with Eclipse MAT and return leak suspects and histograms."""
    path = Path(heap_file).expanduser()
    if path.suffix.lower() not in {".hprof", ".heapdump"}:
        return {"status": "error", "message": "Heap dump must end with .hprof or .heapdump"}
    try:
        settings = Settings.from_env()
        analysis = parse_mat_pages(str(path), mat_script=settings.mat_parse_script)
        return {
            "status": "success",
            "heap_file": str(path),
            "analysis": analysis["results"],
        }
    except Exception as exc:  # noqa: BLE001 - surface MAT errors to the agent
        return {"status": "error", "message": str(exc)}
