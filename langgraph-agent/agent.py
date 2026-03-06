"""LangGraph agent with OpenMemory tools — callable via FastAPI."""

import os
import uuid
import logging
from typing import Annotated

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from memory_tools import ALL_TOOLS, search_memory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("langgraph-agent")

SYSTEM_PROMPT = (
    "You are Arthas's personal AI assistant with access to long-term memory. "
    "Before answering questions, ALWAYS search memory first to check for relevant context. "
    "When the user shares important information (preferences, decisions, facts), store it. "
    "Be concise and helpful. Use Chinese when the user writes in Chinese."
)


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


def build_agent():
    llm = ChatOpenAI(
        model=os.getenv("LLM_MODEL", "qwen-plus"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL", "https://millionengine.com/v1"),
        temperature=0.7,
    )
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    def call_model(state: AgentState):
        messages = state["messages"]
        if not any(isinstance(m, SystemMessage) for m in messages):
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
        return {"messages": [llm_with_tools.invoke(messages)]}

    def should_continue(state: AgentState):
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", ToolNode(ALL_TOOLS))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()


AGENT = build_agent()


async def run_agent(prompt: str, user_id: str = "arthaszeng") -> dict:
    """Run the agent with a user prompt and return the response."""
    task_id = str(uuid.uuid4())[:8]
    logger.info(f"[{task_id}] Running agent for user={user_id}: {prompt[:80]}")

    try:
        memory_context = search_memory.invoke({"query": prompt, "user_id": user_id})
    except Exception:
        memory_context = ""

    enriched_prompt = prompt
    if memory_context and "No relevant memories" not in memory_context:
        enriched_prompt = f"[Relevant memories]\n{memory_context}\n\n[User question]\n{prompt}"

    result = await AGENT.ainvoke(
        {"messages": [HumanMessage(content=enriched_prompt)]},
    )

    last_msg = result["messages"][-1]
    response_text = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
    logger.info(f"[{task_id}] Done, response length={len(response_text)}")

    return {
        "task_id": task_id,
        "response": response_text,
        "message_count": len(result["messages"]),
    }
