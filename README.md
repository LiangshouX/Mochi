# Mochi Agent

```
  ███╗   ███╗  ██████╗  ██████╗ ██╗  ██╗██╗     █████╗ ██╗
  ████╗ ████║ ██╔═══██╗██╔═══██╗██║  ██║██║    ██╔══██╗██║
  ██╔████╔██║ ██║   ██║██║   ██║███████║██║    ███████║██║
  ██║╚██╔╝██║ ██║   ██║██║   ██║██╔══██║██║    ██╔══██║██║
  ██║ ╚═╝ ██║ ╚██████╔╝╚██████╔╝██║  ██║███████╗██║  ██║██║
  ╚═╝     ╚═╝  ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝
```

**Mochi** — 本地运行的个人 AI 助手，基于 LangGraph 构建，支持多模型、长期记忆、MCP 工具扩展和技能系统。

## ✨ 功能特性

- **多模型支持** — DeepSeek、DashScope（阿里云）、OpenAI，其他供应商可通过 OpenAI 兼容模式接入
- **长期记忆** — 跨会话的持久化记忆系统，支持标签和搜索
- **MCP 集成** — 通过 Model Context Protocol 连接外部工具服务器
- **技能系统** — 基于 YAML frontmatter 的 `.md` 技能文件，可扩展
- **交互式 REPL** — 基于 Rich + prompt_toolkit 的终端交互界面，支持多行输入
- **内置工具** — 文件操作、Shell 命令、Web 搜索

## 🚀 快速安装

### 方式一：PyPI 包安装（推荐）

```bash
# 创建 conda 环境
conda create -n mochi python=3.12 -y
conda activate mochi

# 安装
pip install mochi-agent

# 启动
mochi
```

### 方式二：源码运行

```bash
# 克隆仓库
git clone https://github.com/LiangshouX/Mochi.git
cd Mochi

# 创建 conda 环境
conda create -n mochi python=3.12 -y
conda activate mochi

# 安装 Poetry（如尚未安装）
pip install poetry

# 安装依赖
poetry install

# 启动
python -m mochi_agent
```

## ⚙️ 配置

首次运行会在 `~/.mochi/config/config.json` 自动生成默认配置模板：

```json
{
  "mochi": {
    "provider": "openai",
    "model": "deepseek-chat",
    "temperature": 0.7,
    "max_tokens": 4096,
    "api_key": "sk-your-api-key-here",
    "base_url": null
  },
  "security": {
    "allowed_directories": ["~"],
    "dangerous_commands": ["rm -rf", "del /f /s /q", "format", "mkfs"],
    "confirm_dangerous": true
  },
  "mcp": {
    "servers": {}
  }
}
```

修改 `mochi.api_key` 和 `mochi.provider` / `mochi.model` 即可切换模型。

### 支持的 LLM 供应商

| 供应商 | provider 值 | base_url | 模型示例 |
|--------|-------------|----------|----------|
| DeepSeek | `deepseek` | `https://api.deepseek.com` | deepseek-chat, deepseek-coder, deepseek-reasoner |
| DashScope（阿里云） | `dashscope` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | qwen-turbo, qwen-plus, qwen-max, qwen-long |
| OpenAI | `openai` | （默认） | gpt-4o, gpt-4o-mini, gpt-4-turbo |

> **OpenAI 兼容模式**：如需使用其他供应商（如 Anthropic、Google、Ollama 等），可将 `provider` 设为 `openai`，并配置对应的 `base_url` 和 `api_key`，即可通过 OpenAI 兼容接口接入。

## 📖 REPL 命令

| 命令 | 说明 |
|------|------|
| `/new` | 创建新会话 |
| `/sessions` | 列出会话（上下选择切换） |
| `/save` | 保存当前会话 |
| `/model` | 交互式选择模型 |
| `/skills` | 列出已安装的 SKILL |
| `/mcp` | 显示 MCP Server 列表 |
| `/mcp-new` | 添加新的 MCP Server |
| `/memories` | 列出长期记忆 |
| `/forget KEY` | 删除指定记忆 |
| `/config` | 显示当前配置 |
| `/help` | 显示帮助 |
| `/exit` | 退出 |

## 📁 工作区结构

运行后自动创建 `~/.mochi/` 工作区：

```
~/.mochi/
├── config/
│   └── config.json          # 主配置文件
├── memory/
│   ├── sessions/            # 会话历史
│   └── long_term/           # 长期记忆存储
├── skills/                  # 技能文件 (.md)
└── logs/                    # 运行日志
```

## 🏗️ 项目结构

```
mochi_agent/
├── __main__.py              # python -m mochi_agent 入口
├── config.py                # Pydantic 配置模型 + ConfigManager
├── logging_config.py        # 日志配置
├── cli/
│   └── app.py               # REPL 界面 (MochiREPL)
├── agent/
│   ├── core.py              # LangGraph Agent 状态图
│   ├── llm.py               # LLM 工厂（多供应商抽象）
│   └── prompts.py           # 系统提示词
├── memory/
│   ├── session.py           # 短期记忆（会话）
│   └── long_term.py         # 长期记忆（持久化）
├── tools/
│   ├── __init__.py          # ToolRegistry 工具注册表
│   ├── file_ops.py          # 文件操作工具
│   ├── shell.py             # Shell 命令工具
│   └── web_search.py        # Web 搜索工具
├── mcp/
│   ├── client.py            # MCP 客户端
│   ├── config.py            # MCP 配置模型
│   └── auth.py              # MCP 认证
├── skills/
│   ├── schema.py            # Skill 数据模型
│   ├── loader.py            # 技能文件加载器
│   └── executor.py          # 技能执行器
└── storage/
    ├── json_store.py         # JSON 持久化存储
    └── workspace.py          # 工作区管理
```

## 🔧 开发

```bash
# 安装开发依赖
poetry install --with dev

# 运行测试
pytest

# 构建 PyPI 包
python scripts/build.py

# 清理并重新构建
python scripts/build.py --clean
```

## 📄 License

MIT License
