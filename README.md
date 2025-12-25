# CapybaraVibeCoding

AI-powered coding assistant CLI with multi-provider support.

## Features

- **Multi-Provider Support**: Works with OpenAI, Anthropic, Google, Ollama, and 100+ models via LiteLLM
- **Streaming Responses**: Real-time token-by-token output
- **Tool Calling**: Built-in tools for file operations, bash execution, and search
- **MCP Integration**: Support for Model Context Protocol servers
- **Memory Management**: Sliding window with token-based trimming

## Installation

```bash
pip install capybara-vibe-coding
```

Or install from source:

```bash
pip install -e ".[dev]"
```

## Quick Start

```bash
# Initialize configuration
capybara init

# Start interactive chat
capybara chat

# Run a single prompt
capybara run "What files are in this directory?"
```

## Configuration

Configuration is stored in `~/.capybara/config.yaml`:

```yaml
providers:
  - name: openai
    model: gpt-4o
    # api_key: set via OPENAI_API_KEY env var

memory:
  max_tokens: 100000
  persist: true

tools:
  bash_enabled: true
  bash_timeout: 120
```

## Built-in Tools

- `read_file`: Read file contents with line numbers
- `write_file`: Write content to files
- `edit_file`: Edit files with string replacement
- `bash`: Execute bash commands
- `glob`: Find files by pattern
- `grep`: Search file contents

## License

MIT
