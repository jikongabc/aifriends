import os
from typing import TypedDict, Annotated, Sequence

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.constants import START, END
from langgraph.graph import add_messages, StateGraph


# 记忆蒸馏 graph：单节点，调一次 LLM 把对话压缩成长期记忆。
class MemoryGraph:
    # 构建并编译单节点记忆 graph。
    @staticmethod
    def create_app():
        llm = ChatOpenAI(
            model="deepseek-v3.2",
            openai_api_key=os.getenv("API_KEY"),
            openai_api_base=os.getenv("API_BASE"),
        )

        class AgentState(TypedDict):
            messages: Annotated[Sequence[BaseMessage], add_messages]

        # agent 节点：调用 LLM 生成蒸馏后的记忆文本。
        def model_call(state: AgentState) -> AgentState:
            res = llm.invoke(state["messages"])
            return {"messages": [res]}

        graph = StateGraph(AgentState)
        graph.add_node("agent", model_call)

        graph.add_edge(START, "agent")
        graph.add_edge("agent", END)

        return graph.compile()
