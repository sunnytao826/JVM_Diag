from __future__ import annotations

from langchain_openai import AzureChatOpenAI, ChatOpenAI

from jvm_diag.config import Settings


def create_llm(settings: Settings | None = None):
    settings = settings or Settings.from_env()
    settings.require_llm()

    if settings.llm_provider == "openai":
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        )

    return AzureChatOpenAI(
        azure_deployment=settings.azure_deployment,
        api_version=settings.azure_api_version,
        api_key=settings.azure_api_key,
        azure_endpoint=settings.azure_endpoint,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
    )
