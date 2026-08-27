from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from jvm_diag.agents.gc import build_gc_agent
from jvm_diag.agents.memory import build_memory_agent
from jvm_diag.agents.thread import build_thread_agent
from jvm_diag.config import Settings
from jvm_diag.llm import create_llm
from jvm_diag.tools.dify_kb import retrieve_from_dify

logger = logging.getLogger(__name__)

PATH_PATTERN = re.compile(
    r'(?:[A-Za-z]:[\\/]|~[/\\]|[.]{0,2}[/\\])[^\s,"\'<>|]+|'
    r'(?:/[^\s,"\'<>|]+)'
)


class FileItem(BaseModel):
    file_path: str = Field(description="Absolute or relative diagnostic file path")
    file_type: str = Field(description="One of: memory, thread, gc")


class ExtractionResult(BaseModel):
    files: list[FileItem] = Field(description="Diagnostic files to analyze")


class AnalysisModule(BaseModel):
    thread_states: Optional[dict[str, int]] = None
    potential_issue: Optional[str] = None
    leak_suspects: Optional[str] = None
    gc_algorithm: Optional[str] = None
    max_pause_ms: Optional[float] = None
    resource_warning: Optional[str] = None
    top_memory_consumers: Optional[list[str]] = None
    recommendations: Optional[Union[str, list[str]]] = None


class OverallDiagnosis(BaseModel):
    system_status: str
    main_issue: str
    recommended_actions: list[str] = Field(min_length=1)


class DiagnosticSummary(BaseModel):
    root_cause_analysis: dict[str, AnalysisModule] = Field(
        description="Keys should be thread, gc, and/or memory"
    )
    overall_diagnosis: OverallDiagnosis


class SmartRootCoordinator:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.from_env()
        self.llm = create_llm(self.settings)
        self.agent_builders = {
            "memory": build_memory_agent,
            "thread": build_thread_agent,
            "gc": build_gc_agent,
        }

    def run(self, user_input: str) -> dict[str, Any]:
        file_items = self._extract_and_classify_files(user_input)
        if not file_items:
            return {"error": "No valid JVM diagnostic files found in the input."}

        valid_items = []
        for item in file_items:
            path = Path(item.file_path).expanduser()
            if path.is_file():
                item.file_path = str(path.resolve())
                valid_items.append(item)
            else:
                logger.warning("Skipping missing file: %s", item.file_path)

        if not valid_items:
            return {"error": "None of the extracted files exist on disk."}

        individual_results = self._run_agents_parallel(valid_items)
        comprehensive = self._synthesize_report(individual_results)
        return {
            "individual_results": individual_results,
            "comprehensive_analysis": comprehensive,
        }

    @staticmethod
    def classify_by_filename(file_path: str) -> str | None:
        name = os.path.basename(file_path).lower()
        if name.endswith(".hprof") or name.endswith(".heapdump"):
            return "memory"
        if name.endswith(".tdump") or name.endswith(".jstack") or name.endswith(".threads"):
            return "thread"
        if "thread" in name or "jstack" in name:
            return "thread"
        if name.endswith(".log") and "gc" in name:
            return "gc"
        if name.endswith(".gclog") or name.endswith(".gc"):
            return "gc"
        return None

    def _extract_and_classify_files(self, user_input: str) -> list[FileItem]:
        parser = JsonOutputParser(pydantic_object=ExtractionResult)
        system_message = (
            "You extract JVM diagnostic file paths that are explicitly mentioned.\n"
            "Never invent paths. Classify by filename only:\n"
            "- memory: .hprof or .heapdump\n"
            "- gc: filename contains gc and ends with .log, or .gclog\n"
            "- thread: .tdump, .jstack, .threads, or name contains thread/jstack\n"
            "If none match, return {\"files\": []}.\n"
            f"{parser.get_format_instructions()}\n"
            "Respond with JSON only."
        )
        try:
            result = (self.llm | parser).invoke(
                [("system", system_message), ("human", user_input)]
            )
            if hasattr(result, "files"):
                raw_files = result.files
            elif isinstance(result, dict):
                raw_files = [FileItem(**item) for item in result.get("files", []) if isinstance(item, dict)]
            else:
                raw_files = []
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM file extraction failed (%s); falling back to regex.", exc)
            raw_files = []
            for match in PATH_PATTERN.findall(user_input):
                expected = self.classify_by_filename(match)
                if expected:
                    raw_files.append(FileItem(file_path=match, file_type=expected))

        validated = []
        for item in raw_files:
            expected = self.classify_by_filename(item.file_path)
            if expected is None:
                logger.warning("Skipping unclassifiable file: %s", item.file_path)
                continue
            if item.file_type != expected:
                logger.info("Correcting type %s: %s -> %s", item.file_path, item.file_type, expected)
                item.file_type = expected
            validated.append(item)
        return validated

    def _run_agents_parallel(self, file_items: list[FileItem]) -> dict[str, str]:
        results: dict[str, str] = {}
        workers = min(3, max(1, len(file_items)))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self._invoke_single_agent, item.file_type, item.file_path): item
                for item in file_items
                if item.file_type in self.agent_builders
            }
            for future in as_completed(futures):
                item = futures[future]
                key = f"{item.file_type}:{item.file_path}"
                timeout = self.settings.timeout_for(item.file_type)
                try:
                    results[key] = future.result(timeout=timeout)
                except Exception as exc:  # noqa: BLE001
                    results[key] = f"Agent execution failed: {exc}"
        return results

    def _invoke_single_agent(self, agent_type: str, file_path: str) -> str:
        agent = self.agent_builders[agent_type](self.settings)
        response = agent.invoke({"input": file_path})
        if isinstance(response, dict):
            return str(response.get("output", response))
        return str(response)

    def _synthesize_report(self, results: dict[str, str]) -> dict[str, Any]:
        valid_reports = {key: value for key, value in results.items() if not value.startswith("Agent execution failed")}
        if not valid_reports:
            return {"error": "All analysis attempts failed."}

        def escape_curly(text: str) -> str:
            return text.replace("{", "{{").replace("}", "}}")

        report_text = "\n".join(
            f"### {key}\n{escape_curly(value)}\n" for key, value in valid_reports.items()
        )
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_dir = self.settings.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        md_filename = f"report_{stamp}.md"
        md_path = output_dir / md_filename
        md_content = f"# JVM diagnostic report\n\nGenerated: {stamp}\n\n{report_text}\n"
        try:
            md_path.write_text(md_content, encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to save markdown report: %s", exc)

        planning_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Generate a SHORT keyword query (under 100 characters) for a JVM knowledge base. "
                    "Use technical terms only, no full sentences.",
                ),
                ("human", f"Diagnostic Reports:\n\n{report_text}\n\nQuery:"),
            ]
        )
        kb_query = (planning_prompt | self.llm).invoke({}).content.strip()
        retrieved_chunks = retrieve_from_dify(kb_query, self.settings)

        parser = PydanticOutputParser(pydantic_object=DiagnosticSummary)
        synthesis_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a senior JVM performance engineer. Correlate the reports. "
                    "Highlight cross-subsystem effects (GC pauses stalling threads, heap pressure causing GC). "
                    "Reply with JSON only.\n{format_instructions}",
                ),
                (
                    "human",
                    f"Reports:\n\n{report_text}\n\nKnowledge base snippets:\n\n{retrieved_chunks}\n",
                ),
            ]
        ).partial(format_instructions=parser.get_format_instructions())

        chain = synthesis_prompt | self.llm.bind(response_format={"type": "json_object"})
        result_content = chain.invoke({}).content
        parsed_summary = json.loads(result_content)
        relative_log = f"./agent_outputs/{md_filename}"
        final_data = {"summary": parsed_summary, "source_log": relative_log}

        dashboard_json = self.settings.dashboard_dir / "data.json"
        dashboard_json.parent.mkdir(parents=True, exist_ok=True)
        dashboard_json.write_text(json.dumps(final_data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Wrote dashboard data to %s", dashboard_json)

        return {
            "summary": parsed_summary,
            "kb_query_used": kb_query,
            "retrieved_chunks": retrieved_chunks,
            "source_log": relative_log,
        }
