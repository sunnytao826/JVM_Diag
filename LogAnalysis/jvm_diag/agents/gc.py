from __future__ import annotations

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate

from jvm_diag.config import PROMPTS_DIR, Settings
from jvm_diag.llm import create_llm
from jvm_diag.tools.gc_log import analyze_gc_log


def build_gc_agent(settings: Settings | None = None) -> AgentExecutor:
    settings = settings or Settings.from_env()
    llm = create_llm(settings)
    few_shots = (PROMPTS_DIR / "gc_few_shot.md").read_text(encoding="utf-8")
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a JVM GC log analyst. Use the analyze_gc_log tool. "
                "Interpret the report using these JVM flags:\n{tech_param}\n\n"
                "Follow this analysis style:\n{few_shots}\n"
                "Do not invent metrics. Reply in the same language as the user input.",
            ),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ]
    ).partial(few_shots=few_shots, tech_param=settings.jvm_params)
    tools = [analyze_gc_log]
    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=False, handle_parsing_errors=True)
