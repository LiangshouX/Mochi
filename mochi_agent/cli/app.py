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

from rich.console import Console
from rich.text import Text
from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from prompt_toolkit.layout import Layout, HSplit, Window
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.layout.processors import BeforeInput
from prompt_toolkit.buffer import Buffer

from mochi_agent.agent.core import MochiAgent
from mochi_agent.config import Config, ConfigManager
from mochi_agent.logging_config import init_default_logging, get_logger
from mochi_agent.storage.workspace import ensure_workspace

logger = get_logger(__name__)

__version__ = "0.1.0"

# ── Prompt Toolkit 样式 ──────────────────────────────────────────────────
_PT_KHAKI = "#C8B896"  # 莫兰迪浅卡其色

# ── Rich 样式常量 ────────────────────────────────────────────────────────
USER_STYLE = "dim white on #2a2a2a"
BOT_STYLE = "cyan"
ERROR_STYLE = "bold red"
CMD_STYLE = "dim #C8B896"

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


def create_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        prog="mochi",
        description="Mochi — 本地运行的个人 AI 助手",
    )
    parser.add_argument("-m", "--message", type=str, help="发送单条消息并退出")
    parser.add_argument("-c", "--continue-session", type=str, metavar="SESSION_ID", help="继续指定的会话")
    parser.add_argument("--config", type=str, help="自定义配置目录路径（默认 ~/.mochi/）")
    parser.add_argument("--version", action="version", version=f"mochi {__version__}")
    return parser


# ══════════════════════════════════════════════════════════════════════════
#  MochiREPL — 核心交互类
# ══════════════════════════════════════════════════════════════════════════

class MochiREPL:
    """Mochi 交互式 REPL — 参照 Claude Code 风格"""

    def __init__(self, agent: MochiAgent):
        self.agent = agent
        self.console = Console()

    # ── 输入（基于 Application 的带边框输入区） ────────────────────────────
    def _prompt(self) -> str:
        """带莫兰迪卡其色实线边框的多行输入区（动态适配终端宽度）"""
        # ── 样式 ──
        style = Style.from_dict({
            "input-text": "#ffffff",
            "cursor": "bg:#ffffff #000000",
        })

        # ── 布局：上边框 ─ 输入区(≤8行) ─ 下边框 ──
        # 用 Window(char=...) 填充整行，prompt_toolkit 自动处理宽度和重绘
        border_top = Window(height=1, char="─", style=_PT_KHAKI)
        border_bottom = Window(height=1, char="─", style=_PT_KHAKI)

        buf = Buffer(multiline=True)

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
        """用户输入 — 浅灰色背景块"""
        lines = text.split("\n")
        formatted = "\n".join(f"  {line}" for line in lines)
        self.console.print()
        self.console.print(Text(formatted, style=USER_STYLE))

    def _print_bot(self, text: str):
        """AI 回复 — 青色"""
        self.console.print()
        self.console.print(Text(f"  {text}", style=BOT_STYLE))

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

    # ── 主循环 ────────────────────────────────────────────────────────────
    def run(self):
        """REPL 主循环"""
        self._print_banner()

        while True:
            # ── 输入区（边框 + 多行输入，Application 内自动渲染） ──
            try:
                user_input = self._prompt()
            except (EOFError, KeyboardInterrupt):
                self.console.print()
                self.console.print(Text("  再见！👋", style="bold white"))
                break

            if not user_input:
                continue

            # 斜杠命令
            if user_input.startswith("/"):
                self._handle_command(user_input)
            else:
                self._handle_chat(user_input)

    # ── 聊天处理 ──────────────────────────────────────────────────────────
    def _handle_chat(self, user_input: str):
        """处理普通对话"""
        self._print_user_block(user_input)
        try:
            response = self.agent.chat(user_input)
            self._print_bot(response)
        except Exception as e:
            logger.error(f"对话出错: {e}")
            self._print_error(str(e))

    # ══════════════════════════════════════════════════════════════════════
    #  斜杠命令处理
    # ══════════════════════════════════════════════════════════════════════

    def _handle_command(self, raw: str):
        """分发斜杠命令"""
        parts = raw.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        dispatch = {
            "/exit": self._cmd_exit, "/quit": self._cmd_exit,
            "/new": self._cmd_new,
            "/sessions": self._cmd_sessions,
            "/save": self._cmd_save,
            "/model": self._cmd_model,
            "/skills": self._cmd_skills,
            "/skill": self._cmd_skills,
            "/mcp": self._cmd_mcp,
            "/mcp-new": self._cmd_mcp_new,
            "/memories": self._cmd_memories,
            "/forget": lambda _: self._cmd_forget(args),
            "/config": self._cmd_config,
            "/help": self._cmd_help,
        }

        handler = dispatch.get(cmd)
        if handler:
            handler(args)
        else:
            self._print_cmd_output(f"\n  ❌ 未知命令: {cmd}。输入 /help 查看可用命令。")

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
        cfg = self.agent.config.mochi
        providers = {
            "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
            "anthropic": ["claude-sonnet-4-20250514", "claude-haiku-4-5-20251001"],
            "deepseek": ["deepseek-chat", "deepseek-coder", "deepseek-reasoner"],
            "zhipu": ["glm-4", "glm-4-flash"],
            "ollama": ["llama3", "qwen2", "mistral"],
            "google": ["gemini-pro", "gemini-1.5-flash"],
        }

        # 选择供应商
        provider_items = [(p, f"{p}  (当前)" if p == cfg.provider else p) for p in providers]
        selected_provider = self._select_from_list("选择供应商", provider_items)
        if not selected_provider:
            return

        # 选择模型
        models = providers.get(selected_provider, [])
        model_items = [(m, f"{m}  (当前)" if m == cfg.model else m) for m in models]
        selected_model = self._select_from_list("选择模型", model_items)
        if not selected_model:
            return

        # 更新配置
        cfg.provider = selected_provider
        cfg.model = selected_model
        self.agent._llm = None  # 重置 LLM 缓存
        self.agent._graph = None  # 重置图缓存
        self.agent.config_manager.save(self.agent.config)
        self._print_cmd_output(f"\n  ✅ 模型已切换: {selected_provider}/{selected_model}")

    # ── /skills ───────────────────────────────────────────────────────────
    def _cmd_skills(self, _=None):
        registry = self._load_skill_registry()
        if not registry:
            self._print_cmd_output("\n  ⚠️ 技能注册表加载失败")
            return
        skills = registry.list_skills()
        if not skills:
            self._print_cmd_output("\n  暂无可用技能（将 .md 技能文件放入 ~/.mochi/skills/ 目录）")
            return
        lines = ["\n  🎯 已安装的 SKILL:"]
        for s in skills:
            action_type = s.metadata.get("ActionType", "RESPONSE")
            desc = (s.description or "无描述")[:45]
            lines.append(f"    {s.name:<22} [{action_type:<10}] {desc}")
        self._print_cmd_output("\n".join(lines))

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
    /help         显示帮助
    /exit         退出"""
        self._print_cmd_output(help_text)

    # ══════════════════════════════════════════════════════════════════════
    #  交互式选择菜单
    # ══════════════════════════════════════════════════════════════════════

    def _select_from_list(self, title: str, items: list[tuple[str, str]]) -> Optional[str]:
        """交互式选择菜单 — 上下箭头选择，回车确认，q 取消

        使用 prompt_toolkit 实现跨平台兼容。

        Args:
            title: 菜单标题
            items: [(value, display_label), ...]

        Returns:
            选中的 value，取消返回 None
        """
        if not items:
            return None

        from prompt_toolkit import Application
        from prompt_toolkit.key_binding import KeyBindings as _KB
        from prompt_toolkit.layout import Layout, HSplit
        from prompt_toolkit.widgets import TextArea
        from prompt_toolkit.layout.controls import FormattedTextControl
        from prompt_toolkit.layout.containers import Window

        cursor = [0]

        def get_menu_text():
            lines = []
            lines.append([("", f"\n  {title}:\n")])
            for i, (val, label) in enumerate(items):
                if i == cursor[0]:
                    lines.append([("bold #00ff00", f"  ❯ {label}\n")])
                else:
                    lines.append([("dim white", f"    {label}\n")])
            lines.append([("dim #888888", "  ↑↓ 选择  Enter 确认  q 取消\n")])
            return lines

        control = FormattedTextControl(get_menu_text)

        kb = _KB()

        @kb.add("up")
        def _(event):
            cursor[0] = max(0, cursor[0] - 1)

        @kb.add("down")
        def _(event):
            cursor[0] = min(len(items) - 1, cursor[0] + 1)

        @kb.add("enter")
        def _(event):
            event.app.exit(result=items[cursor[0]][0])

        @kb.add("q")
        def _(event):
            event.app.exit(result=None)

        @kb.add("c-c")
        def _(event):
            event.app.exit(result=None)

        layout = Layout(Window(control))

        app = Application(
            layout=layout,
            key_bindings=kb,
            full_screen=False,
            erase_when_done=True,
        )

        try:
            return app.run()
        except Exception:
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
            from mochi_agent.skills.loader import SkillRegistry
            from mochi_agent.storage.workspace import get_workspace_subdir
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
    args = parser.parse_args(argv)

    init_default_logging()

    workspace_dir = Path(args.config) if args.config else None
    workspace = ensure_workspace(workspace_dir)
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

    if args.continue_session:
        session = agent.get_session(args.continue_session)
        if session:
            logger.info(f"恢复会话: {session.session_id}")
        else:
            logger.warning(f"会话不存在: {args.continue_session}，创建新会话")

    if args.message:
        run_one_shot(agent, args.message)
    else:
        repl = MochiREPL(agent)
        repl.run()
