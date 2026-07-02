"""
* Time      : 2026/7/2
* Author    : LiangshouX
* File      : core.py
* Function  : LangGraph Agent 核心 — 状态图定义与执行
"""
from typing import Annotated, Any, Dict, List, Optional, Sequence
from typing_extensions import TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from mochi_agent.agent.llm import create_llm
from mochi_agent.agent.prompts import (
    MEMORY_AUGMENTED_PROMPT,
    SYSTEM_PROMPT,
    format_memory_context,
    format_tools_description,
)
from mochi_agent.config import Config
from mochi_agent.logging_config import get_logger
from mochi_agent.memory.session import MessageRole, Session, ShortTermMemory
from mochi_agent.memory.long_term import LongTermMemory
from mochi_agent.tools import ToolRegistry, get_tool_registry

logger = get_logger(__name__)


class AgentState(TypedDict):
    """Agent 图状态"""
    messages: Annotated[list[BaseMessage], add_messages]
    memory_context: list[str]
    session_id: str


class MochiAgent:
    """Mochi Agent — 基于 LangGraph 的对话代理"""

    def __init__(self, config: Config):
        self.config = config
        self.tool_registry = get_tool_registry()
        self.session_memory = ShortTermMemory()
        self.long_term_memory = LongTermMemory()
        self._graph = None
        self._llm = None

    def _get_llm(self):
        """延迟初始化 LLM"""
        if self._llm is None:
            self._llm = create_llm(self.config.mochi)
        return self._llm

    def _build_graph(self) -> StateGraph:
        """构建 LangGraph 状态图"""
        # 获取工具列表
        tools = self.tool_registry.get_langchain_tools()

        # 创建带工具绑定的 LLM
        llm = self._get_llm()
        if tools:
            llm_with_tools = llm.bind_tools(tools)
        else:
            llm_with_tools = llm

        # 定义节点函数
        def retrieve_memory(state: AgentState) -> dict:
            """检索相关长期记忆"""
            messages = state["messages"]
            if not messages:
                return {"memory_context": []}

            # 用最后一条用户消息作为查询
            last_user_msg = None
            for msg in reversed(messages):
                if isinstance(msg, HumanMessage):
                    last_user_msg = msg.content
                    break

            if not last_user_msg:
                return {"memory_context": []}

            try:
                memories = self.long_term_memory.search(last_user_msg)[:5]
                memory_texts = [m.value for m in memories]
                return {"memory_context": memory_texts}
            except Exception as e:
                logger.warning(f"检索记忆失败: {e}")
                return {"memory_context": []}

        def call_llm(state: AgentState) -> dict:
            """调用 LLM 生成回复"""
            messages = state["messages"]
            memory_context = state.get("memory_context", [])

            # 构建系统提示词
            tools_desc = format_tools_description(tools)
            if memory_context:
                memory_text = format_memory_context(memory_context)
                system_content = MEMORY_AUGMENTED_PROMPT.format(
                    memory_context=memory_text,
                    tools_desc=tools_desc,
                )
            else:
                system_content = SYSTEM_PROMPT.format(tools_desc=tools_desc)

            # 组装消息列表（系统提示 + 历史消息）
            full_messages = [SystemMessage(content=system_content)] + list(messages)

            # 调用 LLM
            logger.info(f"调用 LLM, 消息数: {len(full_messages)}")
            response = llm_with_tools.invoke(full_messages)
            return {"messages": [response]}

        def should_use_tools(state: AgentState) -> str:
            """判断是否需要调用工具"""
            messages = state["messages"]
            if not messages:
                return "end"

            last_message = messages[-1]
            # 如果最后一条消息有 tool_calls，进入工具执行节点
            if isinstance(last_message, AIMessage) and last_message.tool_calls:
                return "tools"
            return "end"

        # 构建图
        graph = StateGraph(AgentState)

        # 添加节点
        graph.add_node("retrieve_memory", retrieve_memory)
        graph.add_node("call_llm", call_llm)

        if tools:
            tool_node = ToolNode(tools)
            graph.add_node("tools", tool_node)

        # 定义边
        graph.set_entry_point("retrieve_memory")
        graph.add_edge("retrieve_memory", "call_llm")

        if tools:
            graph.add_conditional_edges(
                "call_llm",
                should_use_tools,
                {
                    "tools": "tools",
                    "end": END,
                },
            )
            graph.add_edge("tools", "call_llm")
        else:
            graph.add_edge("call_llm", END)

        return graph

    def _get_graph(self) -> StateGraph:
        """延迟构建并缓存图"""
        if self._graph is None:
            self._graph = self._build_graph().compile()
        return self._graph

    def chat(self, user_input: str, session: Optional[Session] = None) -> str:
        """同步对话接口

        Args:
            user_input: 用户输入
            session: 可选的会话对象

        Returns:
            Agent 回复文本
        """
        # 获取或创建会话
        if session is None:
            session = self.session_memory.get_or_create_session()

        # 保存用户消息
        session.add_message(MessageRole.USER, user_input)

        # 构建消息历史
        history_messages = []
        for msg in session.messages:
            if msg.role == MessageRole.USER:
                history_messages.append(HumanMessage(content=msg.content))
            elif msg.role == MessageRole.ASSISTANT:
                history_messages.append(AIMessage(content=msg.content))
            # system 和 tool 消息暂不处理

        # 执行图
        graph = self._get_graph()
        state: AgentState = {
            "messages": history_messages,
            "memory_context": [],
            "session_id": session.session_id,
        }

        logger.info(f"开始对话, session={session.session_id}")
        result = graph.invoke(state)

        # 提取回复
        response_messages = result["messages"]
        response_text = ""
        for msg in reversed(response_messages):
            if isinstance(msg, AIMessage) and msg.content:
                response_text = msg.content
                break

        # 保存助手回复
        if response_text:
            session.add_message(MessageRole.ASSISTANT, response_text)
            self.session_memory.save_session(session)

        return response_text

    def remember(self, key: str, value: str, tags: Optional[List[str]] = None) -> None:
        """存储长期记忆"""
        self.long_term_memory.set(key, value, tags or [])
        logger.info(f"存储记忆: {key}")

    def get_session(self, session_id: Optional[str] = None) -> Session:
        """获取或创建会话"""
        return self.session_memory.get_or_create_session(session_id)

    def list_sessions(self) -> list[str]:
        """列出所有会话"""
        return self.session_memory.list_sessions()

    def new_session(self) -> Session:
        """创建新会话"""
        return self.session_memory.create_session()
