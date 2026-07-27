"""
* Time      : 2026/7/27
* Author    : LiangshouX
* File      : turn_record.py
* Function  : 记录单轮对话的过程事件（工具调用、思考内容），
              支持 Ctrl+O / /debug 展示明细
"""
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from rich.console import Group, RenderableType
from rich.text import Text


@dataclass
class ToolEventRecord:
    """单次工具调用记录"""
    name: str
    args: Dict[str, Any] = field(default_factory=dict)
    result_summary: str = ""
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None

    @property
    def elapsed(self) -> float:
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time


@dataclass
class TurnRecord:
    """单轮对话的过程记录"""
    user_input: str = ""
    thinking_text: str = ""
    tool_events: List[ToolEventRecord] = field(default_factory=list)
    final_response: str = ""

    def add_tool_event(self, name: str, args: Dict[str, Any]) -> None:
        """记录一次工具调用开始"""
        self.tool_events.append(ToolEventRecord(name=name, args=args))

    def record_tool_result(self, content: str) -> None:
        """记录最近一次工具调用的结果"""
        if self.tool_events:
            ev = self.tool_events[-1]
            ev.result_summary = content if len(content) <= 400 else content[:400] + "…"
            ev.end_time = time.time()

    def last_tool_elapsed(self) -> float:
        """最近一次工具调用的耗时（秒）"""
        return self.tool_events[-1].elapsed if self.tool_events else 0.0

    def has_detail(self) -> bool:
        """是否有可展示的过程明细"""
        return bool(self.thinking_text or self.tool_events)

    def render_detail(self) -> RenderableType:
        """渲染明细块（思考全文 + 工具入参/结果/耗时）"""
        parts: List[RenderableType] = []
        if self.thinking_text:
            parts.append(Text(f"  ── 💭 思考过程 ({len(self.thinking_text)} 字) ──", style="bold #B8A8C8"))
            parts.append(Text("  " + self.thinking_text.replace("\n", "\n  "), style="dim white"))
        for te in self.tool_events:
            parts.append(Text(f"  ── ⏺ 工具: {te.name} ({te.elapsed:.1f}s) ──", style="bold #C8B896"))
            try:
                args_text = json.dumps(te.args, ensure_ascii=False)
            except Exception:
                args_text = str(te.args)
            if len(args_text) > 200:
                args_text = args_text[:200] + "…"
            parts.append(Text(f"    参数: {args_text}", style="dim"))
            parts.append(Text(f"    结果: {te.result_summary or '(无)'}", style="dim"))
        if not parts:
            return Text("  (本轮无过程详情)", style="dim")
        header = Text("  ╭─ 回合明细 " + "─" * 24, style="dim")
        footer = Text("  ╰" + "─" * 36, style="dim")
        return Group(header, *parts, footer)
