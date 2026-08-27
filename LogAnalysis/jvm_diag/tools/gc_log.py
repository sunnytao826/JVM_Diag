from __future__ import annotations

import json
from pathlib import Path

import requests
from langchain_core.tools import tool

from jvm_diag.config import Settings


@tool
def analyze_gc_log(file_path: str) -> dict:
    """Upload a JVM GC log to GCeasy and return KPI, warnings, and heap peak size."""
    settings = Settings.from_env()
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        return {"status": "error", "message": f"GC log not found: {path}"}
    if not settings.gceasy_api_key:
        return {
            "status": "error",
            "message": "GCEASY_API_KEY is not set. Get a key at https://gceasy.io and add it to .env",
        }

    url = settings.gceasy_api_url
    separator = "&" if "?" in url else "?"
    request_url = f"{url}{separator}apiKey={settings.gceasy_api_key}"

    try:
        with path.open("rb") as handle:
            response = requests.post(request_url, files={"file": (path.name, handle)}, timeout=120)
        response.raise_for_status()
        result = response.json()
    except requests.RequestException as exc:
        return {"status": "error", "message": f"GCeasy request failed: {exc}"}
    except json.JSONDecodeError:
        return {"status": "error", "message": "GCeasy returned a non-JSON response"}

    gc_kpi = result.get("gcKPI") or {}
    gc_stats = result.get("gcStatistics") or {}
    heap_total = (result.get("jvmHeapSize") or {}).get("total") or {}

    return {
        "status": "success",
        "isProblem": result.get("isProblem"),
        "fatals": result.get("fatals", []),
        "problem": result.get("problem"),
        "warnings": result.get("warnings", []),
        "graphURL": result.get("graphURL"),
        "gcKPI": {
            "throughputPercentage": gc_kpi.get("throughputPercentage"),
            "averagePauseTime": gc_kpi.get("averagePauseTime"),
            "maxPauseTime": gc_kpi.get("maxPauseTime"),
        },
        "gcStatistics": {
            "avgAllocationRate": gc_stats.get("avgAllocationRate"),
            "totalCreatedBytes": gc_stats.get("totalCreatedBytes"),
            "avgPromotionRate": gc_stats.get("avgPromotionRate"),
        },
        "heapPeakSize": heap_total.get("peakSize"),
    }
