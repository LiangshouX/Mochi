# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Mochi is a local personal AI assistant built with LangGraph and LangChain. It features an interactive CLI REPL, long-term memory, MCP (Model Context Protocol) integration, and a skill system.

## Tech Stack

- **Python 3.12+** with Pydantic v2 for data models
- **LangGraph** for agent state graph orchestration
- **LangChain** for LLM abstraction and tool binding
- **MCP SDK** for connecting to external tool servers
- **Rich** + **prompt_toolkit** for terminal UI (styled REPL with bordered input)
- **Poetry** for dependency management (PEP 621 `[project]` metadata, build backend: `poetry.core.masonry.api`)

## Environment

使用 conda 管理 Python 环境，环境名为 `mochi`。

```bash
conda activate mochi
```

## Commands

```bash
# Run the assistant (interactive REPL)
python -m mochi_assistant

# After pip install, use the CLI command directly
mochi

# Single message mode
python -m mochi_assistant -m "your message here"

# Continue a specific session
python -m mochi_assistant -c SESSION_ID

# Custom workspace directory (default ~/.mochi/)
python -m mochi_assistant --config /path/to/workspace

# Install dependencies (source mode)
poetry install
poetry install --with dev    # + pytest, pytest-asyncio

# Tests — no tests/ directory exists yet; CI tolerates pytest exit code 5 (no tests collected)
pytest
pytest tests/test_specific.py   # once tests exist
pytest -k "test_name"

# Build PyPI package
python scripts/build.py
python scripts/build.py --clean
```

## CI

PRs to `main` run GitHub Actions (`.github/workflows/ci.yml`): pytest on a Python 3.12/3.13 matrix, passing even when no tests are collected (`pytest -v || [ $? -eq 5 ]`). `release.yml` handles publishing — see `docs/CI_AND_RELEASE_GUIDE.md`.

## Architecture

### Layer Structure

```
cli/app.py          → REPL interface (MochiREPL) + CLI entry (main)
cli/turn_record.py  → Per-turn process records (tool calls, thinking) for Ctrl+O detail view
agent/core.py       → LangGraph agent (MochiAgent, state graph, chat_stream events)
agent/llm.py        → LLM factory (provider abstraction)
agent/prompts.py    → System prompts and memory formatting
memory/             → Short-term (session JSONL) + long-term (persistent KV) memory
tools/              → Built-in tools (file_ops, shell, web_search) + ToolRegistry
mcp/                → MCP client (SSE transport) for external tool servers
skills/             → Skill system (YAML frontmatter .md files)
storage/            → JSONStore persistence + workspace init (~/.mochi/)
config.py           → Pydantic config models + ConfigManager
```

### Agent Graph Flow

The LangGraph state graph is built in `MochiAgent._build_graph` (`agent/core.py`):

1. **retrieve_memory** → Searches long-term memory with the last user message as query, takes top 5
2. **call_llm** → Builds the system prompt (memory-augmented variant if memories were found) + message history, invokes the LLM with tools bound
3. **tools** (conditional via `should_use_tools`) → LangGraph `ToolNode` executes if the AIMessage has `tool_calls`, then loops back to `call_llm`; otherwise ends. If no tools are registered, `call_llm` edges straight to END.

The LLM is lazily created (`_get_llm`) with `streaming=True`. The REPL consumes the graph via `MochiAgent.chat_stream()`, which streams `graph.stream(state, stream_mode=["updates", "messages"])` as typed `TurnEvent`s (TOKEN / THINKING / TOOL_CALL_START / TOOL_RESULT / DONE / ERROR); `chat()` is a thin non-streaming wrapper over it. Thinking = deepseek-reasoner's `reasoning_content` from chunk `additional_kwargs`. Session persistence happens exactly once, inside `chat_stream`. `MochiAgent.reload_config(config)` swaps the config, drops the cached LLM, and rebuilds the graph — the REPL only calls it when `ConfigManager.reload_if_changed()` detects an mtime change.

### REPL Rendering

`MochiREPL._handle_chat` renders a turn under `rich.Live`: process info (tool calls, thinking counters) appears as dim one-line summaries, the reply streams as plain text, and on completion the text is replaced by a `rich.Markdown` render. `TurnRecord` (cli/turn_record.py) stores each turn's tool args/results/thinking text — **Ctrl+O** at the prompt prints the previous turn's detail (buffered input is restored), and `/debug` toggles inline detail after every turn. Slash commands come from a single `COMMAND_REGISTRY` (completion + dispatch + aliases) plus loaded skill commands; completion auto-triggers while typing (`complete_while_typing=True`).

### LLM Providers — Important Gotcha

All providers in `agent/llm.py` (`openai`, `deepseek`, `dashscope`) map to the **same class** `langchain_openai.ChatOpenAI`; the provider key only selects a default model, and differentiation happens via `base_url`. Other vendors work by setting provider `openai` + a custom `base_url`.

**`langchain-openai` is NOT declared in `pyproject.toml` dependencies.** It is imported dynamically by `create_llm` and raises `ImportError` with an install hint if missing. After a fresh `poetry install`, the agent cannot start until `pip install langchain-openai` is run.

### Memory System

- **ShortTermMemory** (`memory/session.py`): Sessions (UUID-identified) persisted as JSONL at `~/.mochi/memory/sessions/{session_id}.jsonl` — first line is a `_meta` record, then one JSON line per message. `SessionManager` is a CLI-compat wrapper.
- **LongTermMemory** (`memory/long_term.py`): Persistent key-value store with tags over `JSONStore`, under `~/.mochi/memory/long_term/`. `MemoryManager` is a CLI-compat wrapper.

### Configuration

Config lives at `~/.mochi/config/config.json` (created from a default template on first run) with three sections:
- `mochi`: LLM provider, model, temperature, max_tokens, api_key, base_url
- `security`: allowed_directories, dangerous_commands, confirm_dangerous
- `mcp`: MCP server configurations

`main()` attaches the `ConfigManager` onto the agent instance (`agent.config_manager = config_manager`) so REPL commands (`/model`, `/mcp-new`) can persist changes and call `reload_config`. If `mochi` config is incomplete at startup, the REPL drops into interactive setup (`_setup_model_interactive`).

### Tool System

Tools are registered in a global singleton `ToolRegistry` from `get_tool_registry()` (`tools/__init__.py`). Each tool: name, description, input_schema, handler, source (`builtin` or MCP server ID). Built-in tools are registered at `MochiAgent` construction via `register_builtin_tools()` (idempotent); the agent graph consumes the registry via `get_langchain_tools()`, which wraps sync handlers as `StructuredTool(func=...)` and async handlers (MCP) as `StructuredTool(coroutine=...)`.

To add a new built-in tool:
1. Create handler function in `mochi_assistant/tools/`
2. Register via `get_tool_registry().register(name, description, handler, input_schema)`

### MCP Integration

MCP servers are configured under `mcp.servers` in `config.json`. The client (`mcp/client.py`) connects via **SSE** (`mcp.client.sse.sse_client`, with auth headers from `mcp/auth.py`), discovers tools, and registers them into the shared ToolRegistry as `mcp_{server_id}_{tool_name}`.

### Skill System

Skills are `.md` files in `~/.mochi/skills/` with YAML frontmatter (`name`, `command`, `description`, `action`, `parameters`) and an instruction-template body. `SkillRegistry` (`skills/loader.py`) keys skills by slash command; invalid skills are loaded but marked disabled. Execution goes through `skills/executor.py`.

## Workspace Structure

Default workspace `~/.mochi/` (override with `--config`; auto-created by `ensure_workspace`):
- `config/` — `config.json`
- `memory/sessions/` — session history (JSONL)
- `memory/long_term/` — persistent memory (JSON via JSONStore)
- `skills/` — skill definition files (.md)
- `logs/` — runtime logs

## Conventions

- Docstrings, comments, log messages, and user-facing REPL text are written in **Chinese** — match the existing style when editing.
- This repo uses **Spec Kit** (`.specify/` + `speckit-*` skills) for spec-driven development; the project constitution at `.specify/memory/constitution.md` is still the unfilled template.

## REPL Commands

The interactive REPL supports slash commands: `/new`, `/sessions`, `/save`, `/model`, `/skills`, `/mcp`, `/mcp-new`, `/memories`, `/forget`, `/config`, `/debug`, `/help`, `/exit` (plus installed skill commands). Slash input shows an auto-completion menu (arrow keys + Enter). Ctrl+O expands the previous turn's process detail; `-v`/`-vv` raise console log verbosity (default WARNING; full INFO always goes to `~/.mochi/logs/mochi.log`).

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
<!-- SPECKIT END -->
