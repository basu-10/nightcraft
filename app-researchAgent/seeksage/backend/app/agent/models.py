from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ReactState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    available_tools: list[str]
    step_count: int
    max_steps: int
    final_answer: str | None
    used_model: str
    user_id: str
    workspace_id: str
    session_id: str
    run_id: str
