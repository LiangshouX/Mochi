"""
* Time      : 2026/7/2
* Author    : LiangshouX
* File      : app.py
* Function  : CLI 交互式 REPL — 参照 Claude Code 的终端交互体验
"""
import argparse
import sys
from pathlib import Path
from typing import Optional, List

from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.padding import Padding
from rich.text import Text
from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from prompt_toolkit.layout import Layout, HSplit, Window
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.layout.processors import BeforeInput
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import Completer, Completion

from mochi_assistant.agent.core import MochiAgent, TurnEvent, TurnEventType
from mochi_assistant.cli.turn_record import TurnRecord
from mochi_assistant.config import Config, ConfigManager
from mochi_assistant.logging_config import init_default_logging, get_logger
from mochi_assistant.storage.workspace import ensure_workspace

logger = get_logger(__name__)

__version__ = "0.1.0"

# ── Prompt Toolkit 样式 ──────────────────────────────────────────────────
_PT_KHAKI = "#C8B896"  # 莫兰迪浅卡其色

# ── Rich 样式常量 ────────────────────────────────────────────────────────
USER_STYLE = "bold white on #3a3a3a"
USER_MARKER = "❯"
BOT_STYLE = "cyan"
ERROR_STYLE = "bold red"
CMD_STYLE = "dim #C8B896"
PROCESS_STYLE = "dim #8a8a7a"       # 过程信息（工具调用等）弱样式
THINKING_STYLE = "dim #B8A8C8"      # 思考信息弱样式（莫兰迪灰紫）

# ── 莫兰迪配色方案 ──────────────────────────────────────────────────────
_MORANDI_ROSE = "#C4A882"      # 莫兰迪暖棕/玫瑰
_MORANDI_KHAKI = "#C8B896"     # 莫兰迪卡其
_MORANDI_SAGE = "#A8B8A8"      # 莫兰迪灰绿
_MORANDI_LAVENDER = "#B8A8C8"  # 莫兰迪灰紫
_MORANDI_BLUE = "#9AABB8"      # 莫兰迪灰蓝

# ── ASCII Art Logo ───────────────────────────────────────────────────────
_LOGO_LINES = [
    "  ███╗   ███╗  ██████╗  ██████╗ ██╗  ██╗██╗     █████╗ ██╗",
    "  ████╗ ████║ ██╔═══██╗██╔═══██╗██║  ██║██║    ██╔══██╗██║",
    "  ██╔████╔██║ ██║   ██║██║   ██║███████║██║    ███████║██║",
    "  ██║╚██╔╝██║ ██║   ██║██║   ██║██╔══██║██║    ██╔══██║██║",
    "  ██║ ╚═╝ ██║ ╚██████╔╝╚██████╔╝██║  ██║███████╗██║  ██║██║",
    "  ╚═╝     ╚═╝  ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝",
]

# ── 供应商配置 ────────────────────────────────────────────────────────────
_PROVIDERS = {
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "models": ["deepseek-chat", "deepseek-coder", "deepseek-reasoner"],
    },
    "dashscope": {
        "name": "DashScope (阿里云)",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-turbo", "qwen-plus", "qwen-max", "qwen-long"],
    },
    "openai": {
        "name": "OpenAI",
        "base_url": None,
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    },
}

# ── 斜杠命令注册表（补全 / 分发 / 别名的单一数据源） ─────────────────────
COMMAND_REGISTRY = {
    "/new":       {"desc": "创建新会话",              "aliases": []},
    "/sessions":  {"desc": "列出会话（上下选择切换）", "aliases": []},
    "/save":      {"desc": "保存当前会话",            "aliases": []},
    "/model":     {"desc": "选择模型（交互式）",       "aliases": []},
    "/skills":    {"desc": "列出已安装的 SKILL",      "aliases": ["/skill"]},
    "/mcp":       {"desc": "显示 MCP Server 列表",    "aliases": []},
    "/mcp-new":   {"desc": "添加新的 MCP Server",     "aliases": []},
    "/memories":  {"desc": "列出长期记忆",            "aliases": []},
    "/forget":    {"desc": "删除指定记忆 /forget KEY", "aliases": []},
    "/config":    {"desc": "显示当前配置",            "aliases": []},
    "/debug":     {"desc": "切换过程详情内联显示",     "aliases": []},
    "/help":      {"desc": "显示帮助",               "aliases": []},
    "/exit":      {"desc": "退出",                   "aliases": ["/quit"]},
}


class MochiCompleter(Completer):
    """斜杠命令前缀匹配补全器（内置命令 + 技能命令）"""

    def __init__(self, extra_commands: Optional[List[tuple]] = None):
        # extra_commands: [(command, desc), ...] — 来自技能注册表
        self._extra = extra_commands or []

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        # 仅在单行且以 / 开头时触发（多行正文不补全）
        if not text.startswith("/") or "\n" in text:
            return

        for cmd, info in COMMAND_REGISTRY.items():
            if cmd.startswith(text):
                yield Completion(
                    cmd,
                    start_position=-len(text),
                    display_meta=info["desc"],
                )
            for alias in info["aliases"]:
                if alias.startswith(text):
                    yield Completion(
                        alias,
                        start_position=-len(text),
                        display_meta=f"(别名 → {cmd})",
                    )

        for cmd, desc in self._extra:
            if cmd.startswith(text):
                yield Completion(
                    cmd,
                    start_position=-len(text),
                    display_meta=desc or "技能",
                )


# Ctrl+O（展开上一回合明细）哨兵值：_prompt 返回该值表示按下了 Ctrl+O
_CTRL_O_SENTINEL = "\x00__CTRL_O__\x00"


def _summarize_args(args: dict, max_len: int = 60) -> str:
    """把工具入参摘要成一行短文本"""
    try:
        text = ", ".join(f"{k}={v!r}" for k, v in list(args.items())[:3])
    except Exception:
        text = str(args)
    if len(text) > max_len:
        text = text[:max_len] + "…"
    return text


def create_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        prog="mochi",
        description="Mochi — 本地运行的个人 AI 助手",
    )
    parser.add_argument("-m", "--message", type=str, help="发送单条消息并退出")
    parser.add_argument("-c", "--continue-session", type=str, metavar="SESSION_ID", help="继续指定的会话")
    parser.add_argument("--config", type=str, help="自定义配置目录路径（默认 ~/.mochi/）")
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="提升日志详细度（-v 显示 INFO，-vv 显示 DEBUG）")
    parser.add_argument("--version", action="version", version=f"mochi {__version__}")
    return parser


# ══════════════════════════════════════════════════════════════════════════
#  MochiREPL — 核心交互类
# ══════════════════════════════════════════════════════════════════════════

class MochiREPL:
    """Mochi 交互式 REPL — 参照 Claude Code 风格"""

    def __init__(self, agent: MochiAgent):
        self.agent = agent
        self.console = Console(force_terminal=True)
        # 上一回合的过程记录（供 Ctrl+O 展开明细）
        self._last_turn: Optional[TurnRecord] = None
        # /debug 开启后，每回合结束内联展示过程明细
        self._show_debug_inline: bool = False
        # Ctrl+O 打断输入时暂存的残文（下次 _prompt 回填）
        self._pending_input: str = ""
        # 技能注册表缓存（启动时加载一次，供命令分发与补全复用）
        self._skill_registry = self._load_skill_registry()
        if self._skill_registry is not None:
            try:
                self._skill_registry.load_all()
            except Exception as e:
                logger.warning(f"加载技能失败: {e}")
        # 斜杠命令补全器（内置命令 + 技能命令）
        extra_cmds = []
        if self._skill_registry is not None:
            for skill in self._skill_registry.list_skills():
                extra_cmds.append((skill.command, skill.description or "技能"))
        self._completer = MochiCompleter(extra_commands=extra_cmds)
        # 确保输出流使用 UTF-8 编码（Windows 默认可能是 ASCII）
        if hasattr(self.console.file, 'reconfigure'):
            try:
                self.console.file.reconfigure(encoding='utf-8')
            except Exception:
                pass

    # ── 输入（基于 Application 的带边框输入区） ────────────────────────────
    def _prompt(self, default: str = "") -> str:
        """带莫兰迪卡其色实线边框的多行输入区（动态适配终端宽度）

        Args:
            default: 预填文本（用于 Ctrl+O 展开明细后回填之前的输入残文）

        Returns:
            用户输入文本；按下 Ctrl+O 时返回 _CTRL_O_SENTINEL
        """
        # ── 样式 ──
        style = Style.from_dict({
            "input-text": "#ffffff",
            "cursor": "bg:#ffffff #000000",
            # 补全菜单（莫兰迪配色）
            "completion-menu": "bg:#2f2f2f #C8B896",
            "completion-menu.completion.current": "bg:#A8B8A8 #000000",
            "completion-menu.meta": "bg:#2f2f2f #8a8a7a",
            "completion-menu.meta.current": "bg:#A8B8A8 #333333",
            "completion-menu.scrollbar.background": "bg:#2f2f2f",
            "completion-menu.scrollbar.button": "bg:#C8B896",
        })

        # ── 布局：上边框 ─ 输入区(≤8行) ─ 下边框 ──
        # 用 Window(char=...) 填充整行，prompt_toolkit 自动处理宽度和重绘
        border_top = Window(height=1, char="─", style=_PT_KHAKI)
        border_bottom = Window(height=1, char="─", style=_PT_KHAKI)

        buf = Buffer(
            multiline=True,
            completer=self._completer,
            complete_while_typing=True,  # 输入 / 后自动弹出补全菜单
        )
        if default:
            buf.text = default  # 光标自动置于文末

        input_area = Window(
            height=Dimension(min=1, max=8),
            content=BufferControl(
                buffer=buf,
                input_processors=[
                    BeforeInput(" > ", style="bold #55aa55"),
                ],
            ),
        )

        layout = Layout(HSplit([border_top, input_area, border_bottom]))

        # ── 键绑定 ──
        kb = KeyBindings()

        @kb.add("enter")
        def _(event):
            buffer = event.app.current_buffer
            text = buffer.text
            if text.rstrip().endswith("\\"):
                buffer.delete_backward_char(1)
                buffer.insert_text("\n")
            else:
                buffer.validate_and_handle()

        @kb.add("escape", "enter")
        def _(event):
            event.app.current_buffer.insert_text("\n")

        @kb.add("c-c")
        def _(event):
            buffer = event.app.current_buffer
            if buffer.text:
                buffer.reset()
            else:
                raise KeyboardInterrupt

        @kb.add("c-o")
        def _(event):
            # Ctrl+O：展开上一回合明细。暂存输入残文，主循环打印明细后回填
            self._pending_input = event.app.current_buffer.text
            event.app.exit(result=_CTRL_O_SENTINEL)

        # ── 构建 Application ──
        app = Application(
            layout=layout,
            key_bindings=kb,
            style=style,
            full_screen=False,
            erase_when_done=True,
        )

        # accept_handler 在 app 创建之后设置，确保 app 可用
        buf.accept_handler = lambda buffer: app.exit(result=buffer.text)

        try:
            result = app.run()
            return (result or "").strip()
        except KeyboardInterrupt:
            raise
        except EOFError:
            raise

    def _print_user_block(self, text: str):
        """用户输入 — 亮灰底粗体块，首行带 ❯ 标记"""
        lines = text.split("\n")
        formatted = "\n".join(
            f"  {USER_MARKER} {line}" if i == 0 else f"    {line}"
            for i, line in enumerate(lines)
        )
        self.console.print()
        self.console.print(Text(formatted, style=USER_STYLE))

    def _print_bot(self, text: str):
        """AI 回复 — Markdown 排版渲染"""
        self.console.print()
        self.console.print(Padding(Markdown(text), (0, 0, 0, 2)))

    def _print_cmd_output(self, text: str):
        """命令输出"""
        self.console.print()
        self.console.print(Text(text, style=CMD_STYLE))

    def _print_error(self, text: str):
        """错误信息"""
        self.console.print()
        self.console.print(Text(f"  ⚠ {text}", style=ERROR_STYLE))

    # ── Banner ────────────────────────────────────────────────────────────
    @staticmethod
    def _build_logo() -> Text:
        """构建莫兰迪配色的 ASCII Art Logo"""
        logo = Text()
        # 莫兰迪色彩渐变：按行循环分配颜色
        colors = [_MORANDI_ROSE, _MORANDI_KHAKI, _MORANDI_SAGE,
                  _MORANDI_LAVENDER, _MORANDI_BLUE, _MORANDI_KHAKI]
        for i, line in enumerate(_LOGO_LINES):
            if i > 0:
                logo.append("\n")
            logo.append(line, style=colors[i % len(colors)])
        return logo

    def _print_banner(self):
        cfg = self.agent.config.mochi
        session = self.agent.get_session()
        self.console.print()
        self.console.print(self._build_logo())
        self.console.print()
        self.console.print(Text(f"  v{__version__}  ·  {cfg.provider}/{cfg.model}", style="dim #C8B896"))
        self.console.print(Text(f"  会话: {session.session_id[:12]}  ·  输入 /help 查看命令", style="dim #C8B896"))

    # ── 配置校验与交互式配置 ──────────────────────────────────────────────
    @staticmethod
    def _validate_config(cfg) -> tuple[bool, str]:
        """校验模型配置是否可用

        Returns:
            (valid, reason) — valid=False 时 reason 说明缺失项
        """
        api_key = cfg.api_key
        if not api_key or api_key.strip() in ("", "sk-your-api-key-here"):
            return False, "未配置 API Key"
        if not cfg.provider or not cfg.provider.strip():
            return False, "未选择供应商"
        if not cfg.model or cfg.model.strip() in ("", "deepseek-v4-pro"):
            return False, "未选择模型"
        return True, ""

    def _setup_model_interactive(self) -> bool:
        """交互式模型配置（三步：选供应商 → 选模型 → 填 API Key）

        Returns:
            是否配置成功
        """
        self.console.print()
        self.console.print(Text("  ⚙️  首次使用，请配置模型", style="bold white"))
        self.console.print()

        # Step 1: 选择供应商
        provider_items = [
            (pid, f"{p['name']}  ({pid})") for pid, p in _PROVIDERS.items()
        ]
        selected_provider = self._select_from_list("选择供应商", provider_items)
        if not selected_provider:
            return False

        provider_info = _PROVIDERS[selected_provider]

        # Step 2: 选择模型
        models = provider_info["models"]
        model_items = [(m, m) for m in models]
        model_items.append(("[custom]", "[ 自定义输入 ]"))
        selected_model = self._select_from_list("选择模型", model_items)

        if not selected_model:
            return False

        if selected_model == "[custom]":
            custom_model = self._prompt_simple("  模型名称")
            if not custom_model:
                return False
            selected_model = custom_model

        # Step 3: 输入 API Key
        self.console.print()
        api_key = self._prompt_simple("  API Key", is_password=True)
        if not api_key:
            return False

        # 写入配置
        cfg = self.agent.config.mochi
        cfg.provider = selected_provider
        cfg.model = selected_model
        cfg.api_key = api_key
        cfg.base_url = provider_info["base_url"]

        self.agent.config_manager.save(self.agent.config)
        self.agent.reload_config(self.agent.config)

        self.console.print()
        self.console.print(Text(
            f"  ✅ 已配置: {provider_info['name']} / {selected_model}",
            style="bold #A8B8A8",
        ))
        return True

    # ── 主循环 ────────────────────────────────────────────────────────────
    def run(self):
        """REPL 主循环"""
        self._print_banner()

        pending = ""
        while True:
            # ── 输入区（边框 + 多行输入，Application 内自动渲染） ──
            try:
                user_input = self._prompt(default=pending)
            except (EOFError, KeyboardInterrupt):
                self.console.print()
                self.console.print(Text("  再见！👋", style="bold white"))
                break
            pending = ""

            # Ctrl+O：展开上一回合的过程明细，随后回填残文继续输入
            if user_input == _CTRL_O_SENTINEL:
                pending = self._pending_input
                self._pending_input = ""
                if self._last_turn and self._last_turn.has_detail():
                    self.console.print()
                    self.console.print(self._last_turn.render_detail())
                else:
                    self._print_cmd_output("\n  (暂无上一轮对话的过程详情)")
                continue

            if not user_input:
                continue

            # 斜杠命令
            if user_input.startswith("/"):
                self._handle_command(user_input)
            else:
                self._handle_chat(user_input)

    # ── 聊天处理 ──────────────────────────────────────────────────────────
    def _handle_chat(self, user_input: str):
        """处理普通对话（配置文件变化时才热更新）"""
        # 条件热更新：仅当 config.json 发生变化时重新加载
        try:
            new_config = self.agent.config_manager.reload_if_changed()
            if new_config is not None:
                self.agent.reload_config(new_config)
                logger.info("检测到配置变化，Agent 配置已热更新")
        except Exception as e:
            logger.warning(f"配置热更新失败: {e}")

        # 校验配置
        valid, reason = self._validate_config(self.agent.config.mochi)
        if not valid:
            self._print_error(f"模型配置不完整: {reason}")
            self._print_cmd_output("  请使用 /model 命令配置模型，或手动编辑 ~/.mochi/config/config.json")
            return

        # 清理输入中的控制字符和非法字符
        clean_input = user_input.encode("utf-8", errors="ignore").decode("utf-8")
        clean_input = "".join(ch for ch in clean_input if ch == "\n" or ch == "\r" or (ord(ch) >= 32 and ord(ch) != 127))

        self._print_user_block(clean_input)

        # ── 流式对话渲染 ────────────────────────────────────────────────
        # 过程信息（工具调用/思考）以弱样式摘要行折叠显示；回复先逐 token
        # 流出纯文本，回合结束后整体替换为 Markdown 排版
        turn_record = TurnRecord(user_input=clean_input)
        self._last_turn = turn_record
        process_lines: List[Text] = []   # 折叠的过程摘要行
        token_buffer = ""                # 累积的回复文本
        thinking_buffer = ""             # 累积的思考文本

        def _response_part() -> Text:
            if token_buffer:
                return Text("  " + token_buffer, style=BOT_STYLE)
            if thinking_buffer:
                return Text("  ⏳ 思考中…", style=THINKING_STYLE)
            return Text("  ⏳ …", style=PROCESS_STYLE)

        def _build_display(response_renderable) -> Group:
            parts: list = list(process_lines)
            if thinking_buffer:
                parts.append(Text(
                    f"  💭 已思考 {len(thinking_buffer)} 字 · Ctrl+O 展开",
                    style=THINKING_STYLE,
                ))
            parts.append(response_renderable)
            return Group(*parts)

        try:
            with Live(Text(""), console=self.console, refresh_per_second=10, transient=False) as live:
                for event in self.agent.chat_stream(clean_input):
                    if event.type == TurnEventType.TOKEN:
                        token_buffer += event.content
                        live.update(_build_display(_response_part()))
                    elif event.type == TurnEventType.THINKING:
                        thinking_buffer += event.content
                        turn_record.thinking_text += event.content
                        live.update(_build_display(_response_part()))
                    elif event.type == TurnEventType.TOOL_CALL_START:
                        turn_record.add_tool_event(event.tool_name, event.tool_args)
                        process_lines.append(Text(
                            f"  ⏺ 调用工具 {event.tool_name}({_summarize_args(event.tool_args)}) …",
                            style=PROCESS_STYLE,
                        ))
                        live.update(_build_display(_response_part()))
                    elif event.type == TurnEventType.TOOL_RESULT:
                        turn_record.record_tool_result(event.content)
                        if process_lines:
                            elapsed = turn_record.last_tool_elapsed()
                            process_lines[-1] = Text(
                                f"  ⏺ 调用工具 {event.tool_name} … ok {elapsed:.1f}s",
                                style=PROCESS_STYLE,
                            )
                        live.update(_build_display(_response_part()))
                    elif event.type == TurnEventType.ERROR:
                        raise event.error
                    # DONE：落到下面的最终渲染

                # 最终渲染：回复区替换为 Markdown 排版（留在屏幕上）
                final_parts: list = list(process_lines)
                if thinking_buffer:
                    final_parts.append(Text(
                        f"  💭 已思考 {len(thinking_buffer)} 字 · Ctrl+O 展开",
                        style=THINKING_STYLE,
                    ))
                if token_buffer:
                    final_parts.append(Padding(Markdown(token_buffer), (0, 0, 0, 2)))
                live.update(Group(*final_parts) if final_parts else Text(""))
        except KeyboardInterrupt:
            # Ctrl+C 中断：保留已流出的内容
            if token_buffer:
                self.console.print(Text("  " + token_buffer, style="dim"))
            self._print_error("对话已中断")
            return
        except Exception as e:
            logger.error(f"对话出错: {e}")
            self._print_error(str(e))
            return

        turn_record.final_response = token_buffer

        # /debug 模式：内联展示本回合过程明细
        if self._show_debug_inline and turn_record.has_detail():
            self.console.print(turn_record.render_detail())

    # ══════════════════════════════════════════════════════════════════════
    #  斜杠命令处理
    # ══════════════════════════════════════════════════════════════════════

    def _handle_command(self, raw: str):
        """分发斜杠命令"""
        parts = raw.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        dispatch = {
            "/exit": self._cmd_exit,
            "/new": self._cmd_new,
            "/sessions": self._cmd_sessions,
            "/save": self._cmd_save,
            "/model": self._cmd_model,
            "/skills": self._cmd_skills,
            "/mcp": self._cmd_mcp,
            "/mcp-new": self._cmd_mcp_new,
            "/memories": self._cmd_memories,
            "/forget": lambda _: self._cmd_forget(args),
            "/config": self._cmd_config,
            "/debug": self._cmd_debug,
            "/help": self._cmd_help,
        }

        # 别名解析（如 /quit → /exit，/skill → /skills）
        resolved = cmd
        for canonical, info in COMMAND_REGISTRY.items():
            if cmd == canonical or cmd in info["aliases"]:
                resolved = canonical
                break

        handler = dispatch.get(resolved)
        if handler:
            handler(args)
        else:
            # 兜底：尝试匹配已安装的技能命令（如 /commit）
            self._try_skill_command(cmd, args)

    # ── /exit ─────────────────────────────────────────────────────────────
    def _cmd_exit(self, _=None):
        self.console.print()
        self.console.print(Text("  再见！👋", style="bold white"))
        sys.exit(0)

    # ── /new ──────────────────────────────────────────────────────────────
    def _cmd_new(self, _=None):
        session = self.agent.new_session()
        self._print_cmd_output(f"\n  ✅ 已创建新会话: {session.session_id[:12]}")

    # ── /sessions — 交互式选择 ────────────────────────────────────────────
    def _cmd_sessions(self, _=None):
        sessions = self.agent.list_sessions()
        if not sessions:
            self._print_cmd_output("\n  暂无历史会话")
            return

        # 构建会话信息列表
        items = []
        for sid in sessions:
            session = self.agent.session_memory.load_session(sid)
            if session:
                msg_count = len(session.messages)
                try:
                    if hasattr(session.update_at, 'strftime'):
                        last_active = session.update_at.strftime("%m-%d %H:%M")
                    else:
                        last_active = str(session.update_at)[:16]
                except Exception:
                    last_active = ""
                label = f"{sid[:12]}  |  {msg_count} 条消息  |  {last_active}"
            else:
                label = sid[:12]
            items.append((sid, label))

        # 交互式选择
        selected = self._select_from_list("选择会话", items)
        if selected:
            session = self.agent.get_session(selected)
            if session:
                self._print_cmd_output(f"\n  ✅ 已切换到会话: {selected[:12]}  ({len(session.messages)} 条消息)")
            else:
                self._print_error(f"会话不存在: {selected}")

    # ── /save ─────────────────────────────────────────────────────────────
    def _cmd_save(self, _=None):
        session = self.agent.get_session()
        self.agent.session_memory.save_session(session)
        self._print_cmd_output(f"\n  ✅ 会话已保存: {session.session_id[:12]}")

    # ── /model — 选择模型 ─────────────────────────────────────────────────
    def _cmd_model(self, _=None):
        """交互式模型配置"""
        self._setup_model_interactive()

    # ── /skills ───────────────────────────────────────────────────────────
    def _cmd_skills(self, _=None):
        registry = self._skill_registry
        if not registry:
            self._print_cmd_output("\n  ⚠️ 技能注册表加载失败")
            return
        skills = registry.list_skills()
        if not skills:
            self._print_cmd_output("\n  暂无可用技能（将 .md 技能文件放入 ~/.mochi/skills/ 目录）")
            return
        lines = ["\n  🎯 已安装的 SKILL:"]
        for s in skills:
            action_type = s.action.type.value
            desc = (s.description or "无描述")[:45]
            lines.append(f"    {s.command:<14} {s.name:<18} [{action_type:<8}] {desc}")
        self._print_cmd_output("\n".join(lines))

    # ── 技能命令执行 ─────────────────────────────────────────────────────
    def _try_skill_command(self, cmd: str, args: str) -> bool:
        """尝试匹配并执行技能命令；未匹配时提示未知命令

        Args:
            cmd: 斜杠命令（如 /commit）
            args: 命令参数

        Returns:
            是否匹配到技能
        """
        skill = self._skill_registry.get(cmd) if self._skill_registry else None
        if skill is None:
            self._print_cmd_output(f"\n  ❌ 未知命令: {cmd}。输入 /help 查看可用命令。")
            return False
        if not skill.enabled:
            self._print_error(f"技能 {cmd} 已被禁用")
            return True

        # 按参数定义顺序解析位置参数
        arguments = {}
        if args:
            params = getattr(skill, "_parameters", []) or []
            for i, value in enumerate(args.split()):
                if i < len(params):
                    arguments[params[i].get("name", f"arg{i}")] = value
                else:
                    arguments.setdefault("_extra", []).append(value)

        self._print_cmd_output(f"\n  ⏺ 使用技能 {cmd}")
        try:
            from mochi_assistant.skills.executor import execute_skill
            from mochi_assistant.skills.schema import ActionType
            result = execute_skill(skill, arguments=arguments, body=getattr(skill, "_body", ""))
        except NotImplementedError as e:
            self._print_error(f"技能执行暂未实现: {e}")
            return True
        except Exception as e:
            logger.error(f"技能执行失败: {e}")
            self._print_error(f"技能执行失败: {e}")
            return True

        if skill.action.type == ActionType.RESPONSE:
            # RESPONSE：渲染后的指令正文作为本轮用户消息交给 Agent（走流式对话）
            self._handle_chat(result)
        else:
            # SHELL / HTTP / FUNCTION：弱样式展示执行结果
            self._print_cmd_output("\n" + (result or "(无输出)"))
        return True

    # ── /mcp — 列出 MCP Server ───────────────────────────────────────────
    def _cmd_mcp(self, _=None):
        servers = self.agent.config.mcp.servers
        if not servers:
            self._print_cmd_output("\n  暂无已配置的 MCP Server（使用 /mcp-new 添加）")
            return
        lines = ["\n  🔌 已配置的 MCP Server:"]
        for name, srv in servers.items():
            url = srv.get("url", "?")
            auth = srv.get("auth_type", "api_key")
            enabled = "✅" if srv.get("enabled", True) else "❌"
            lines.append(f"    {enabled} {name:<20} {url:<40} [{auth}]")
        self._print_cmd_output("\n".join(lines))

    # ── /mcp-new — 交互式配置 MCP Server ─────────────────────────────────
    def _cmd_mcp_new(self, _=None):
        self.console.print()
        self.console.print(Text("  🔌 添加新的 MCP Server", style="bold white"))
        self.console.print()

        try:
            name = self._prompt_simple("  Server 名称")
            if not name:
                return
            url = self._prompt_simple("  Server URL (SSE)")
            if not url:
                return

            # 选择认证类型
            auth_items = [
                ("api_key", "API Key"),
                ("bearer", "Bearer Token"),
                ("none", "无需认证"),
            ]
            auth_type = self._select_from_list("认证类型", auth_items) or "none"

            auth_config = {}
            if auth_type == "api_key":
                api_key = self._prompt_simple("  API Key", is_password=True)
                auth_config = {"api_key": api_key}
            elif auth_type == "bearer":
                token = self._prompt_simple("  Bearer Token", is_password=True)
                auth_config = {"token": token}

            # 保存到配置
            self.agent.config.mcp.servers[name] = {
                "name": name,
                "url": url,
                "auth_type": auth_type,
                "auth_config": auth_config,
                "enabled": True,
            }
            self.agent.config_manager.save(self.agent.config)
            self._print_cmd_output(f"\n  ✅ MCP Server '{name}' 已添加")
        except KeyboardInterrupt:
            self._print_cmd_output("\n  已取消")

    # ── /memories ─────────────────────────────────────────────────────────
    def _cmd_memories(self, _=None):
        memories = self.agent.long_term_memory.list_memories()
        if not memories:
            self._print_cmd_output("\n  暂无长期记忆")
            return
        lines = ["\n  🧠 长期记忆:"]
        for mem in memories:
            tags = ", ".join(mem.tags) if mem.tags else "无标签"
            value_preview = mem.value[:50] + ("..." if len(mem.value) > 50 else "")
            lines.append(f"    [{mem.key}] {value_preview}  (标签: {tags})")
        self._print_cmd_output("\n".join(lines))

    # ── /forget ───────────────────────────────────────────────────────────
    def _cmd_forget(self, args: str):
        if not args:
            self._print_cmd_output("\n  用法: /forget <memory_key>")
            return
        key = args.strip()
        if self.agent.long_term_memory.delete(key):
            self._print_cmd_output(f"\n  ✅ 已删除记忆: {key}")
        else:
            self._print_error(f"记忆不存在: {key}")

    # ── /config ───────────────────────────────────────────────────────────
    def _cmd_config(self, _=None):
        cfg = self.agent.config.mochi
        key_display = ('***' + cfg.api_key[-4:]) if cfg.api_key and len(cfg.api_key) > 4 else '(未设置)'
        lines = [
            "\n  ⚙️  当前配置:",
            f"    provider   : {cfg.provider}",
            f"    model      : {cfg.model}",
            f"    base_url   : {cfg.base_url or '(默认)'}",
            f"    api_key    : {key_display}",
            f"    temperature: {cfg.temperature}",
            f"    max_tokens : {cfg.max_tokens}",
        ]
        self._print_cmd_output("\n".join(lines))

    # ── /debug ───────────────────────────────────────────────────────────
    def _cmd_debug(self, _=None):
        """切换过程明细内联显示（工具调用/思考内容）"""
        self._show_debug_inline = not self._show_debug_inline
        state = "开启" if self._show_debug_inline else "关闭"
        self._print_cmd_output(f"\n  🔧 过程详情内联显示: {state}（Ctrl+O 可随时展开上一回合明细）")

    # ── /help ─────────────────────────────────────────────────────────────
    def _cmd_help(self, _=None):
        help_text = """
  📖 可用命令:

    /new          创建新会话
    /sessions     列出会话（上下选择切换）
    /save         保存当前会话
    /model        选择模型（交互式）
    /skills       列出已安装的 SKILL
    /mcp          显示 MCP Server 列表
    /mcp-new      添加新的 MCP Server
    /memories     列出长期记忆
    /forget KEY   删除指定记忆
    /config       显示当前配置
    /debug        切换过程详情内联显示
    /help         显示帮助
    /exit         退出

  ⌨️  快捷键:  Ctrl+O 展开上一回合明细  ·  Alt+Enter 换行  ·  行尾 \\ 续行"""
        self._print_cmd_output(help_text)

    # ══════════════════════════════════════════════════════════════════════
    #  交互式选择菜单
    # ══════════════════════════════════════════════════════════════════════

    def _select_from_list(self, title: str, items: list[tuple[str, str]]) -> Optional[str]:
        """交互式选择菜单 — 上下箭头选择，回车确认，q 取消

        Args:
            title: 菜单标题
            items: [(value, display_label), ...]

        Returns:
            选中的 value，取消返回 None
        """
        if not items:
            return None

        cursor = [0]
        total_lines = len(items) + 2  # 标题 + 选项 + 提示

        def _render():
            """用 Rich 渲染菜单"""
            self.console.print(f"\n  {title}:", style="bold white")
            for i, (_, label) in enumerate(items):
                if i == cursor[0]:
                    self.console.print(f"  ❯ {label}", style="bold #00ff00")
                else:
                    self.console.print(f"    {label}", style="dim white")
            self.console.print("  ↑↓ 选择  Enter 确认  q 取消", style="dim #888888")

        def _redraw():
            """清除旧菜单并重绘"""
            # 用 Rich 的控制移动光标上移并清除
            for _ in range(total_lines):
                self.console.file.write("\r\033[A\033[2K")
            self.console.file.flush()
            _render()

        # 首次渲染
        _render()

        try:
            import msvcrt
            while True:
                ch = msvcrt.getwch()
                if ch in ("\x00", "\xe0"):
                    ch2 = msvcrt.getwch()
                    if ch2 == "H":    # Up
                        cursor[0] = max(0, cursor[0] - 1)
                    elif ch2 == "P":  # Down
                        cursor[0] = min(len(items) - 1, cursor[0] + 1)
                elif ch in ("\r", "\n"):
                    for _ in range(total_lines):
                        self.console.file.write("\r\033[A\033[2K")
                    self.console.file.flush()
                    return items[cursor[0]][0]
                elif ch in ("q", "\x03"):
                    for _ in range(total_lines):
                        self.console.file.write("\r\033[A\033[2K")
                    self.console.file.flush()
                    return None
                else:
                    continue
                _redraw()
        except ImportError:
            import tty, termios
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                while True:
                    ch = sys.stdin.read(1)
                    if ch == "\x1b":
                        ch2 = sys.stdin.read(1)
                        if ch2 == "[":
                            ch3 = sys.stdin.read(1)
                            if ch3 == "A":
                                cursor[0] = max(0, cursor[0] - 1)
                            elif ch3 == "B":
                                cursor[0] = min(len(items) - 1, cursor[0] + 1)
                    elif ch in ("\r", "\n"):
                        for _ in range(total_lines):
                            self.console.file.write("\r\033[A\033[2K")
                        self.console.file.flush()
                        return items[cursor[0]][0]
                    elif ch in ("q", "\x03"):
                        for _ in range(total_lines):
                            self.console.file.write("\r\033[A\033[2K")
                        self.console.file.flush()
                        return None
                    else:
                        continue
                    _redraw()
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except KeyboardInterrupt:
            return None

    def _prompt_simple(self, label: str, is_password: bool = False) -> Optional[str]:
        """简单单行输入提示"""
        try:
            if is_password:
                import getpass
                return getpass.getpass(f"  {label}: ").strip()
            return self.console.input(f"  {label}: ").strip()
        except (KeyboardInterrupt, EOFError):
            return None

    # ── Skill 加载 ────────────────────────────────────────────────────────
    @staticmethod
    def _load_skill_registry():
        try:
            from mochi_assistant.skills.loader import SkillRegistry
            from mochi_assistant.storage.workspace import get_workspace_subdir
            skills_dir = get_workspace_subdir("skills")
            return SkillRegistry(skills_dir)
        except Exception as e:
            logger.warning(f"加载技能注册表失败: {e}")
            return None


# ══════════════════════════════════════════════════════════════════════════
#  主入口
# ══════════════════════════════════════════════════════════════════════════

def run_one_shot(agent: MochiAgent, message: str) -> None:
    """单条消息模式"""
    try:
        response = agent.chat(message)
        print(response)
    except Exception as e:
        logger.error(f"对话出错: {e}")
        print(f"⚠ 出错了: {e}", file=sys.stderr)
        sys.exit(3)


def main(argv: Optional[list] = None) -> None:
    """CLI 主入口"""
    parser = create_parser()

    # Windows 控制台默认可能是 GBK，统一切到 UTF-8，避免 emoji 等字符输出报错
    # （需在 parse_args 之前，--help/--version 的输出也走这里）
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    args = parser.parse_args(argv)

    # 先准备工作区，再初始化日志（确保文件日志落到 ~/.mochi/logs/）
    workspace_dir = Path(args.config) if args.config else None
    workspace = ensure_workspace(workspace_dir)

    # 控制台日志级别：默认 WARNING，-v → INFO，-vv+ → DEBUG
    import logging as _logging
    console_level = {0: _logging.WARNING, 1: _logging.INFO}.get(args.verbose, _logging.DEBUG)
    init_default_logging(workspace, console_level=console_level)

    logger.info(f"工作区: {workspace}")

    config_manager = ConfigManager(workspace)
    config = config_manager.load()

    try:
        agent = MochiAgent(config)
        agent.config_manager = config_manager  # 挂载到 agent 上供 /model、/mcp-new 保存配置
    except Exception as e:
        logger.error(f"Agent 初始化失败: {e}")
        print(f"⚠ Agent 初始化失败: {e}", file=sys.stderr)
        sys.exit(1)

    # 连接配置中的 MCP 服务器（失败非致命，不阻断启动）
    try:
        from mochi_assistant.mcp.client import connect_mcp_servers_sync
        connect_mcp_servers_sync(config.mcp, agent.tool_registry)
    except Exception as e:
        logger.warning(f"MCP 启动失败（非致命）: {e}")

    if args.continue_session:
        session = agent.get_session(args.continue_session)
        if session:
            logger.info(f"恢复会话: {session.session_id}")
        else:
            logger.warning(f"会话不存在: {args.continue_session}，创建新会话")

    if args.message:
        # 单条消息模式：也校验配置
        valid, reason = MochiREPL._validate_config(config.mochi)
        if not valid:
            print(f"⚠ 模型配置不完整: {reason}", file=sys.stderr)
            print("  请先运行 mochi 进入交互式配置", file=sys.stderr)
            sys.exit(1)
        run_one_shot(agent, args.message)
    else:
        repl = MochiREPL(agent)

        # 启动时校验配置，不通过则进入交互式配置
        valid, reason = MochiREPL._validate_config(config.mochi)
        if not valid:
            configured = repl._setup_model_interactive()
            if not configured:
                repl._print_error("未完成配置，部分功能不可用。可随时使用 /model 重新配置。")

        repl.run()
