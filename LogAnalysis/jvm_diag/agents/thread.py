from __future__ import annotations

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate

from jvm_diag.config import PROMPTS_DIR, Settings
from jvm_diag.llm import create_llm
from jvm_diag.tools.thread_dump import analyze_thread_dump_hybrid


def build_thread_agent(settings: Settings | None = None) -> AgentExecutor:
    settings = settings or Settings.from_env()
    llm = create_llm(settings)
    few_shots = (PROMPTS_DIR / "thread_few_shot.md").read_text(encoding="utf-8")
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a JVM thread-dump expert. Use analyze_thread_dump_hybrid. "
                "Follow this style:\n{few_shots}\nDo not invent deadlocks or lock owners.",
            ),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ]
    ).partial(few_shots=few_shots)
    tools = [analyze_thread_dump_hybrid]
    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=False, handle_parsing_errors=True)
