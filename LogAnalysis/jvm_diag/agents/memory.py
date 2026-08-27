from __future__ import annotations

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate

from jvm_diag.config import PROMPTS_DIR, Settings
from jvm_diag.llm import create_llm
from jvm_diag.tools.heap import analyze_heap_dump


def build_memory_agent(settings: Settings | None = None) -> AgentExecutor:
    settings = settings or Settings.from_env()
    llm = create_llm(settings)
    few_shots = (PROMPTS_DIR / "memory_few_shot.md").read_text(encoding="utf-8")
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a senior Java performance engineer. Use analyze_heap_dump, "
                "explain MAT findings in the user's language, and follow this style:\n{few_shots}\n"
                "Never invent class names or heap sizes.",
            ),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ]
    ).partial(few_shots=few_shots)
    tools = [analyze_heap_dump]
    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=False, handle_parsing_errors=True)
