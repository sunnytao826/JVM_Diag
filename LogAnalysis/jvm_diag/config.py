from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent
PROMPTS_DIR = PACKAGE_DIR / "prompts"


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value is None:
        return None
    value = value.strip()
    return value or default


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    azure_deployment: str
    azure_api_version: str
    azure_api_key: str | None
    azure_endpoint: str | None
    openai_api_key: str | None
    openai_model: str
    temperature: float
    max_tokens: int
    gceasy_api_key: str | None
    gceasy_api_url: str
    dify_api_key: str | None
    dify_dataset_id: str | None
    dify_api_url: str | None
    dify_top_k: int
    mat_parse_script: str | None
    tda_jar_path: str
    jvm_params: str
    dashboard_dir: Path
    output_dir: Path
    agent_timeout_gc: int
    agent_timeout_thread: int
    agent_timeout_memory: int

    @classmethod
    def from_env(cls) -> "Settings":
        dashboard_dir = Path(_env("DASHBOARD_DIR", str(PROJECT_ROOT / "dashboard"))).resolve()
        output_dir = Path(_env("AGENT_OUTPUT_DIR", str(dashboard_dir / "agent_outputs"))).resolve()
        params_file = _env("JVM_PARAMS_FILE", str(PROMPTS_DIR / "jvm_params.example.txt"))
        jvm_params = _env("JVM_STARTUP_PARAMS")
        if not jvm_params:
            path = Path(params_file)
            jvm_params = path.read_text(encoding="utf-8") if path.exists() else ""

        return cls(
            llm_provider=(_env("LLM_PROVIDER", "azure") or "azure").lower(),
            azure_deployment=_env("AZURE_OPENAI_DEPLOYMENT", "gpt-4o") or "gpt-4o",
            azure_api_version=_env("AZURE_OPENAI_API_VERSION", "2024-02-01") or "2024-02-01",
            azure_api_key=_env("AZURE_OPENAI_API_KEY"),
            azure_endpoint=_env("AZURE_OPENAI_ENDPOINT"),
            openai_api_key=_env("OPENAI_API_KEY"),
            openai_model=_env("OPENAI_MODEL", "gpt-4o") or "gpt-4o",
            temperature=float(_env("LLM_TEMPERATURE", "0") or "0"),
            max_tokens=int(_env("LLM_MAX_TOKENS", "4096") or "4096"),
            gceasy_api_key=_env("GCEASY_API_KEY"),
            gceasy_api_url=_env("GCEASY_API_URL", "https://gceasy.io/analyzeGC")
            or "https://gceasy.io/analyzeGC",
            dify_api_key=_env("DIFY_API_KEY"),
            dify_dataset_id=_env("DIFY_DATASET_ID"),
            dify_api_url=_env("DIFY_API_URL"),
            dify_top_k=int(_env("DIFY_TOP_K", "3") or "3"),
            mat_parse_script=_env("MAT_PARSE_SCRIPT"),
            tda_jar_path=_env("TDA_JAR_PATH", str(PROJECT_ROOT / "tda-2.6.jar"))
            or str(PROJECT_ROOT / "tda-2.6.jar"),
            jvm_params=jvm_params,
            dashboard_dir=dashboard_dir,
            output_dir=output_dir,
            agent_timeout_gc=int(_env("AGENT_TIMEOUT_GC", "180") or "180"),
            agent_timeout_thread=int(_env("AGENT_TIMEOUT_THREAD", "180") or "180"),
            agent_timeout_memory=int(_env("AGENT_TIMEOUT_MEMORY", "1800") or "1800"),
        )

    def require_llm(self) -> None:
        if self.llm_provider == "openai":
            if not self.openai_api_key:
                raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
            return
        missing = [
            name
            for name, value in (
                ("AZURE_OPENAI_API_KEY", self.azure_api_key),
                ("AZURE_OPENAI_ENDPOINT", self.azure_endpoint),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "Missing required Azure OpenAI settings: "
                + ", ".join(missing)
                + ". Copy .env.example to .env and fill in your credentials."
            )

    def dify_enabled(self) -> bool:
        return bool(self.dify_api_key and self.dify_dataset_id and self.dify_api_url)

    def timeout_for(self, agent_type: str) -> int:
        return {
            "gc": self.agent_timeout_gc,
            "thread": self.agent_timeout_thread,
            "memory": self.agent_timeout_memory,
        }.get(agent_type, 180)
