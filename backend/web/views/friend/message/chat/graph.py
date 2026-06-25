import logging
import os
import threading
from typing import TypedDict, Annotated, Sequence

import lancedb
from django.utils.timezone import localtime, now
from langchain_community.vectorstores import LanceDB
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import START, END
from langgraph.graph import add_messages, StateGraph
from langgraph.prebuilt import ToolNode

from web.documents.utils.custom_embeddings import CustomEmbeddings


logger = logging.getLogger(__name__)

# 模块级单例：graph / 向量库进程内只构建一次跨请求复用（graph 无状态，compile 一次反复 invoke）。
_lock = threading.Lock()
_app = None
_vector_db = None


# 懒加载 LanceDB 向量库单例（双重检查锁，线程安全）。
def _get_vector_db():
    global _vector_db
    if _vector_db is None:
        with _lock:
            if _vector_db is None:
                connection = lancedb.connect('./web/documents/lancedb_storage')
                _vector_db = LanceDB(
                    connection=connection,
                    embedding=CustomEmbeddings(),
                    table_name='my_knowledge_base',
                )
    return _vector_db


# 注意：@tool 的 docstring 会作为工具描述发给 LLM，是功能性内容，勿删改。
@tool
def get_time() -> str:
    """当需要查询精确时间时，调用此函数。返回格式为：[年-月-日 时:分:秒]"""
    return localtime(now()).strftime('%Y-%m-%d %H:%M:%S')


@tool
def search_knowledge_base(query: str) -> str:
    """当用户查询阿里云百炼平台的相关信息时，调用此函数。输入为要查询的问题，输出为查询结果。"""
    # 知识库未建/为空时优雅降级：返回提示而非抛异常，避免拖垮整个 agent。
    try:
        docs = _get_vector_db().similarity_search(query, k=3)
    except Exception:
        logger.exception('search_knowledge_base failed')
        docs = []
    if not docs:
        return '知识库中暂无相关信息，请根据你已有的知识回答。'
    context = '\n\n'.join([f'内容片段：{i + 1}\n{doc.page_content}' for i, doc in enumerate(docs)])
    return f'从知识库中找到以下相关信息：\n\n{context}\n'


TOOLS = [get_time, search_knowledge_base]


# 每轮按 friend 最新画像与长期记忆动态构建系统提示（不入 checkpointer，故记忆更新即时生效）。
def _build_system_prompt(friend) -> SystemMessage:
    from web.models.friend import SystemPrompt

    prompt = ''
    for sp in SystemPrompt.objects.filter(title='回复').order_by('order_number'):
        prompt += sp.prompt
    prompt += f'\n【角色性格】\n{friend.character.profile}\n'
    prompt += f'【长期记忆】\n{friend.memory}\n'
    return SystemMessage(prompt)


# graph 状态：messages 用 add_messages 归约器累加。
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


# 构建并编译 agent→tools→agent 条件循环 graph，绑定工具与 checkpointer。
def _build_app():
    llm = ChatOpenAI(
        model='deepseek-v3.2',
        openai_api_key=os.getenv('API_KEY'),
        openai_api_base=os.getenv('API_BASE'),
        streaming=True,
        model_kwargs={
            "stream_options": {
                "include_usage": True,  # 输出token消耗数量
            }
        }
    ).bind_tools(TOOLS)

    # agent 节点：注入动态系统提示后调用 LLM。
    def model_call(state: AgentState, config) -> AgentState:
        from web.models.friend import Friend

        friend_id = config['configurable']['friend_id']
        friend = Friend.objects.select_related('character').get(pk=friend_id)
        system = _build_system_prompt(friend)
        res = llm.invoke([system] + list(state['messages']))
        return {'messages': [res]}

    # 条件分支：有 tool_calls 则转 tools 节点，否则结束。
    def should_continue(state: AgentState) -> str:
        last_message = state['messages'][-1]
        if last_message.tool_calls:
            return "tools"
        return "end"

    graph = StateGraph(AgentState)
    graph.add_node('agent', model_call)
    graph.add_node('tools', ToolNode(TOOLS))

    graph.add_edge(START, 'agent')
    graph.add_conditional_edges(
        'agent',
        should_continue,
        {
            'tools': 'tools',
            'end': END,
        }
    )
    graph.add_edge('tools', 'agent')

    # MemorySaver 按 thread_id 进程内管理会话；耐久历史以 Message 表为准，生产可换 PostgresSaver。
    return graph.compile(checkpointer=MemorySaver())


# 返回进程内唯一的已编译 graph 单例（双重检查锁）。
def get_app():
    global _app
    if _app is None:
        with _lock:
            if _app is None:
                _app = _build_app()
    return _app


# 兼容旧调用点：内部已改为返回单例，不再每次重建。
class ChatGraph:
    @staticmethod
    def create_app():
        return get_app()
