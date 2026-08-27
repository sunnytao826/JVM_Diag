from __future__ import annotations

import argparse
import json
import logging
import sys

from jvm_diag.config import Settings
from jvm_diag.coordinator import SmartRootCoordinator


def _build_query(args: argparse.Namespace) -> str:
    if args.query:
        return args.query
    parts = ["Please analyze the following JVM diagnostic files:"]
    if args.gc:
        parts.append(f"- GC log: {args.gc}")
    if args.thread:
        parts.append(f"- thread dump: {args.thread}")
    if args.heap:
        parts.append(f"- heap dump: {args.heap}")
    if len(parts) == 1:
        return ""
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="jvm-diag",
        description="Multi-agent JVM diagnostic analyzer (GC log, thread dump, heap dump).",
    )
    parser.add_argument("query", nargs="?", help="Natural-language request that includes file paths")
    parser.add_argument("--gc", help="Path to a GC log")
    parser.add_argument("--thread", help="Path to a thread dump")
    parser.add_argument("--heap", help="Path to a heap dump (.hprof)")
    parser.add_argument("--json", action="store_true", help="Print the full result as JSON")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    user_query = _build_query(args).strip()
    if not user_query:
        parser.error("Provide a query or at least one of --gc / --thread / --heap")

    try:
        settings = Settings.from_env()
        settings.require_llm()
        result = SmartRootCoordinator(settings).run(user_query)
    except ValueError as exc:
        logging.error("%s", exc)
        return 2
    except Exception as exc:  # noqa: BLE001
        logging.exception("Analysis failed: %s", exc)
        return 1

    if args.json or "error" in result:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if "error" in result else 0

    if "individual_results" in result:
        print("\n=== Individual results ===")
        for key, value in result["individual_results"].items():
            print(f"\n[{key}]\n{value}")
        print("\n=== Comprehensive analysis ===")
        comprehensive = result["comprehensive_analysis"]
        print(json.dumps(comprehensive, ensure_ascii=False, indent=2) if isinstance(comprehensive, dict) else comprehensive)
    return 0


if __name__ == "__main__":
    sys.exit(main())
