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
- **Poetry** for dependency management (build backend: `poetry.core.masonry.api`)

## Environment

使用 conda 管理 Python 环境，环境名为 `mochi`。

```bash
conda activate mochi
```

## Commands

```bash
# Run the assistant (interactive REPL)
python -m mochi_agent

# After pip install, use the CLI command directly
mochi

# Single message mode
python -m mochi_agent -m "your message here"
mochi -m "your message here"

# Continue a specific session
python -m mochi_agent -c SESSION_ID

# Custom config directory
python -m mochi_agent --config /path/to/config

# Install dependencies (source mode)
poetry install

# Install dev dependencies
poetry install --with dev

# Run tests (pytest)
pytest
pytest tests/test_specific.py
pytest -k "test_name"

# Build PyPI package
python scripts/build.py
python scripts/build.py --clean
```

## Architecture

### Layer Structure

The codebase follows a layered architecture:

```
cli/app.py          → REPL interface (MochiREPL class)
agent/core.py       → LangGraph agent (MochiAgent class, state graph)
agent/llm.py        → LLM factory (provider abstraction)
agent/prompts.py    → System prompts and memory formatting
memory/             → Short-term (session) + long-term (persistent) memory
tools/              → Built-in tools (file_ops, shell, web_search) + ToolRegistry
mcp/                → MCP client for external tool servers
skills/             → Skill system (YAML frontmatter .md files)
storage/            → JSONStore persistence layer
config.py           → Pydantic config models + ConfigManager
```

### Agent Graph Flow

The LangGraph state graph (`agent/core.py`) follows this flow:

1. **retrieve_memory** → Searches long-term memory for context
2. **call_llm** → Invokes LLM with system prompt + memory context + message history
3. **tools** (conditional) → Executes tool calls if LLM requests them
4. Loops back to `call_llm` after tool execution, or ends

### Memory System

- **ShortTermMemory** (`memory/session.py`): In-memory session storage with message history. Sessions are identified by UUID.
- **LongTermMemory** (`memory/long_term.py`): Persistent key-value store with tags. Stored in `~/.mochi/memory/long_term/` as JSON.

### Configuration

Config is stored at `~/.mochi/config/config.json` with three sections:
- `mochi`: LLM provider, model, temperature, max_tokens, api_key, base_url
- `security`: allowed_directories, dangerous_commands list
- `mcp`: MCP server configurations

Supported LLM providers: openai, anthropic, deepseek, zhipu, ollama, google

### Tool System

Tools are registered via `ToolRegistry` (global singleton from `get_tool_registry()`). Each tool has: name, description, input_schema, handler function, source (builtin or MCP).

To add a new built-in tool:
1. Create handler function in `mochi_agent/tools/`
2. Register via `get_tool_registry().register(name, description, handler, input_schema)`

### MCP Integration

MCP servers are configured in `config.json` under `mcp.servers`. The client (`mcp/client.py`) connects via SSE, discovers tools, and registers them with the ToolRegistry prefixed as `mcp_{server_id}_{tool_name}`.

### Skill System

Skills are `.md` files in `~/.mochi/skills/` with YAML frontmatter defining metadata and action type. The skill loader parses frontmatter and extracts the instruction template from the body.

## Workspace Structure

The default workspace is `~/.mochi/` with subdirectories:
- `config/` — configuration files
- `memory/long_term/` — persistent memory storage
- `skills/` — skill definition files (.md)

## REPL Commands

The interactive REPL supports slash commands: `/new`, `/sessions`, `/save`, `/model`, `/skills`, `/mcp`, `/mcp-new`, `/memories`, `/forget`, `/config`, `/help`, `/exit`
