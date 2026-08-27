from __future__ import annotations

import logging

import requests
from pydantic import BaseModel, Field

from jvm_diag.config import Settings

logger = logging.getLogger(__name__)


class DifyKnowledgeBaseInput(BaseModel):
    query: str = Field(description="Retrieval query for the JVM knowledge base.")


def retrieve_from_dify(query: str, settings: Settings | None = None) -> str:
    """Fetch relevant chunks from a Dify dataset. Returns a note if Dify is not configured."""
    settings = settings or Settings.from_env()
    if not settings.dify_enabled():
        return "Knowledge base skipped: DIFY_API_KEY / DIFY_DATASET_ID / DIFY_API_URL are not all set."

    headers = {
        "Authorization": f"Bearer {settings.dify_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "query": query,
        "retrieval_model": {
            "search_method": "semantic_search",
            "reranking_enable": False,
            "top_k": settings.dify_top_k,
            "score_threshold_enabled": False,
        },
    }
    try:
        response = requests.post(
            f"{settings.dify_api_url.rstrip('/')}/datasets/{settings.dify_dataset_id}/retrieve",
            headers=headers,
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
    except requests.Timeout:
        return "[Knowledge Base Retrieval Failed: request timed out]"
    except requests.RequestException as exc:
        return f"[Knowledge Base Retrieval Failed: {exc}]"

    records = data.get("records") or []
    chunks = []
    for index, record in enumerate(records, 1):
        segment = record.get("segment") or {}
        content = (segment.get("content") or "").strip()
        if not content:
            continue
        doc_name = ((segment.get("document") or {}).get("name")) or "Unknown Document"
        score = record.get("score")
        score_str = f" (score: {score:.3f})" if isinstance(score, (int, float)) else ""
        chunks.append(f"[Chunk {index}{score_str} from '{doc_name}']:\n{content}\n")
    return "\n".join(chunks) if chunks else "No relevant information found in the knowledge base."
