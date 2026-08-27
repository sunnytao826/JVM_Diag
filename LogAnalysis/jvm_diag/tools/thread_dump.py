from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from jvm_diag.config import Settings

logger = logging.getLogger(__name__)


def extract_long_running_threads_from_raw(file_path: str) -> list[dict[str, Any]]:
    try:
        content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return [{"error": f"Read failed: {exc}"}]

    dumps = re.findall(r"(Full thread dump.*?)(?=Full thread dump|\Z)", content, flags=re.DOTALL)
    dumps = [dump.strip() for dump in dumps if dump.strip()]
    if len(dumps) < 2:
        return [{"error": f"Only {len(dumps)} dump(s) found. Expected >=2."}]

    def parse_threads(dump_text: str) -> dict[str, tuple]:
        threads: dict[str, tuple] = {}
        lines = dump_text.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].rstrip()
            if (
                line.startswith("Full thread dump")
                or "Threads class SMR info" in line
                or (line.strip().startswith("0x") and "," in line and len(line.strip()) > 20)
            ):
                i += 1
                continue

            if line.startswith('"') and "#" in line:
                name_match = re.match(r'"([^"]*)"', line)
                name = name_match.group(1) if name_match else "Unknown"
                nid_match = re.search(r"nid=([^,\s\]]+)", line)
                nid = nid_match.group(1) if nid_match else f"fallback_{hash(line)}"
                cpu_time_ms = None
                elapsed_sec = None
                cpu_match = re.search(r"cpu=([\d.]+)ms", line)
                if cpu_match:
                    cpu_time_ms = float(cpu_match.group(1))
                elapsed_match = re.search(r"elapsed=([\d.]+)s", line)
                if elapsed_match:
                    elapsed_sec = float(elapsed_match.group(1))

                state = "UNKNOWN"
                stack: list[str] = []
                j = i + 1
                while j < len(lines):
                    next_line = lines[j].rstrip()
                    if (
                        (next_line.startswith('"') and "#" in next_line)
                        or next_line.startswith("Full thread dump")
                        or "Threads class SMR info" in next_line
                    ):
                        break
                    if "java.lang.Thread.State:" in next_line:
                        parts = next_line.split(":", 1)
                        if len(parts) > 1:
                            state = parts[1].strip().split()[0]
                    elif next_line.strip().startswith("at "):
                        stack.append(next_line.strip())
                    j += 1
                threads[nid] = (name, state, stack, cpu_time_ms, elapsed_sec)
                i = j
            else:
                i += 1
        return threads

    t0 = parse_threads(dumps[0])
    t1 = parse_threads(dumps[1])
    long_running = []
    for nid, thread_info in t0.items():
        if nid not in t1 or len(thread_info) != 5 or len(t1[nid]) != 5:
            continue
        name, state, stack, cpu_time, elapsed = thread_info
        name1, state1, stack1, *_ = t1[nid]
        if state == state1 and stack == stack1 and stack:
            long_running.append(
                {
                    "threadName": name,
                    "nid": nid,
                    "state": state,
                    "cpu_time_ms": cpu_time,
                    "elapsed_sec": elapsed,
                    "stackTrace": stack[:2],
                }
            )
    return long_running or [{"info": "No identical threads found across dumps."}]


def find_hot_runnable_methods(file_path: str, top_n: int = 5) -> list[tuple[str, int]]:
    methods: list[str] = []
    in_runnable = False
    with Path(file_path).open(encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            if line.startswith('"') and "java.lang.Thread.State: RUNNABLE" in line:
                in_runnable = True
                continue
            if line.startswith('"'):
                in_runnable = False
            elif in_runnable and line.strip().startswith("at "):
                method = line.split("(")[0].replace("at ", "")
                methods.append(method)
                in_runnable = False
    return Counter(methods).most_common(top_n)


def get_thread_state_distribution(file_path: str) -> dict[str, int]:
    states: dict[str, int] = {}
    with Path(file_path).open(encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            if "java.lang.Thread.State:" in line:
                state = line.split(":", 1)[1].strip().split()[0]
                states[state] = states.get(state, 0) + 1
    return states


def _call_tda_mcp_batch(file_path: str, jar_path: str) -> dict[str, Any]:
    abs_path = os.path.abspath(file_path)
    requests = [
        {"jsonrpc": "2.0", "method": "parse_log", "params": {"path": abs_path}, "id": 1},
        {"jsonrpc": "2.0", "method": "get_summary", "id": 2},
        {"jsonrpc": "2.0", "method": "check_deadlocks", "id": 3},
        {"jsonrpc": "2.0", "method": "find_long_running", "id": 4},
        {"jsonrpc": "2.0", "method": "analyze_virtual_threads", "id": 5},
        {"jsonrpc": "2.0", "method": "get_native_threads", "params": {"dump_index": 0}, "id": 6},
        {"jsonrpc": "2.0", "method": "get_zombie_threads", "id": 7},
    ]
    input_lines = "\n".join(json.dumps(req) for req in requests) + "\n"
    result = subprocess.run(
        ["java", "-Djava.awt.headless=true", "-jar", jar_path, "--mcp"],
        input=input_lines,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[:500] or "TDA exited with a non-zero status")

    responses = []
    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        try:
            responses.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    response_map = {item["id"]: item.get("result", []) for item in responses if "id" in item}
    return {
        "summary": response_map.get(2, []),
        "deadlocks": response_map.get(3, []),
        "long_running": response_map.get(4, []),
        "virtual_threads": response_map.get(5, []),
        "native_threads": response_map.get(6, []),
        "zombie_threads": response_map.get(7, []),
    }


def _extract_lock_contention(file_path: str) -> list[dict[str, Any]]:
    content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    thread_blocks: list[str] = []
    current: list[str] = []
    for line in content.splitlines():
        if line.startswith('"') and "java.lang.Thread.State" in line:
            if current:
                thread_blocks.append("\n".join(current))
            current = [line]
        elif current:
            current.append(line)
    if current:
        thread_blocks.append("\n".join(current))

    lock_holders: dict[str, str] = {}
    lock_waiters: dict[str, list[str]] = defaultdict(list)
    for block in thread_blocks:
        name_match = re.search(r'"([^"]+)"', block)
        if not name_match:
            continue
        thread_name = name_match.group(1)
        for lock_id in re.findall(r"locked <(0x[0-9a-f]+)>", block):
            lock_holders.setdefault(lock_id, thread_name)
        if "java.lang.Thread.State: BLOCKED" in block:
            wait_match = re.search(r"waiting to lock <(0x[0-9a-f]+)>", block)
            if wait_match:
                lock_waiters[wait_match.group(1)].append(thread_name)

    contention = [
        {
            "lockId": lock_id,
            "holder": lock_holders.get(lock_id, "Unknown (possibly released)"),
            "waiterCount": len(waiters),
            "waiters": waiters,
        }
        for lock_id, waiters in lock_waiters.items()
    ]
    contention.sort(key=lambda item: item["waiterCount"], reverse=True)
    return contention


@tool
def analyze_thread_dump_hybrid(file_path: str) -> dict[str, Any]:
    """Analyze a Java thread dump (.tdump, .jstack, or thread*.txt) for deadlocks, locks, and hot stacks."""
    path = Path(file_path).expanduser()
    if not path.is_file():
        return {"status": "error", "message": f"Thread dump not found: {path}"}

    settings = Settings.from_env()
    tda_result: dict[str, Any] = {
        "summary": [],
        "deadlocks": [],
        "long_running": [],
        "virtual_threads": [],
        "native_threads": [],
        "zombie_threads": [],
    }
    tda_available = Path(settings.tda_jar_path).is_file()
    if tda_available:
        try:
            tda_result = _call_tda_mcp_batch(str(path), settings.tda_jar_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("TDA MCP unavailable, using Python parser only: %s", exc)
            tda_result["deadlocks"] = [f"TDA unavailable: {exc}"]
    else:
        tda_result["deadlocks"] = ["TDA jar not found; deadlock check skipped. Set TDA_JAR_PATH."]

    lock_contention = _extract_lock_contention(str(path))
    tda_long_msg = tda_result.get("long_running") or []
    has_tda_hint = (
        isinstance(tda_long_msg, list)
        and len(tda_long_msg) == 1
        and isinstance(tda_long_msg[0], str)
        and "Long running thread detection between Dump" in tda_long_msg[0]
    )
    long_running_detail = (
        extract_long_running_threads_from_raw(str(path))
        if has_tda_hint
        else tda_long_msg or [{"info": "No TDA long-running-thread hint."}]
    )

    return {
        "status": "success",
        "source": "tda_mcp + python_enhanced" if tda_available else "python_only",
        "input_file": str(path.resolve()),
        "tda_analysis": {
            "summary": tda_result.get("summary", []),
            "deadlocks": tda_result.get("deadlocks", []),
            "long_running": long_running_detail,
            "virtual_threads": tda_result.get("virtual_threads", []),
            "native_threads": tda_result.get("native_threads", []),
            "zombie_threads": tda_result.get("zombie_threads", []),
        },
        "lock_contention": lock_contention,
        "has_lock_contention": bool(lock_contention),
        "total_waiters": sum(item["waiterCount"] for item in lock_contention),
        "status_histogram": get_thread_state_distribution(str(path)),
        "hot_runnable": find_hot_runnable_methods(str(path)),
    }
