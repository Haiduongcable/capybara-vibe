# CLI Interface

Capybara Vibe provides a feature-rich command-line interface built with Click and Rich for an enhanced terminal experience.

## Commands

| Command | Description |
|---------|-------------|
| `capybara` | Start interactive chat session |
| `capybara init` | Initialize configuration via web UI |
| `capybara config` | Show current configuration |
| `capybara model` | Get or set the default AI model |
| `capybara resume` | Resume a previous conversation session |
| `capybara run <prompt>` | Run a single prompt and exit |
| `capybara sessions` | List recent conversation sessions |

## Operation Modes

The CLI supports four operation modes that control agent behavior and permissions:

### Standard Mode (Default)

Balanced autonomy. The agent asks for permission before sensitive actions but proceeds with safe reads automatically.

```bash
capybara
```

### Safe Mode

Maximum control. The agent asks for confirmation before every shell command or file modification.

```bash
capybara --mode safe
```

Safe mode behavior:
- All bash commands require user approval (except allowlisted read-only commands)
- File write, edit, and delete operations require approval
- Allowlisted safe commands: `cat`, `ls`, `pwd`, `git status`, `git diff`, `tree`, etc.

### Plan Mode

Read-only mode for architectural planning and code analysis. The agent cannot modify files.

```bash
capybara --mode plan
```

Plan mode restrictions:
- Write tools are completely hidden (`write_file`, `edit_file`, `delete_file`)
- Todo and sub-agent tools are disabled
- Bash commands are filtered (no `rm`, `mv`, `git commit`, `git push`, etc.)
- Perfect for codebase exploration and planning without risk

### Auto Mode

Maximum autonomy with minimal confirmations. Use with caution.

```bash
capybara --mode auto
```

Auto mode behavior:
- All bash, write, edit, and delete operations proceed without asking
- Useful for scripted workflows or when you fully trust the agent's decisions

## Interactive Session

### Welcome Panel

When starting a session, a professional welcome panel displays:
- Current provider and model
- Working directory
- Session ID
- Quick tips for getting started

### Keybindings

| Key | Action |
|-----|--------|
| `Ctrl+C` | Interrupt current operation |
| `Ctrl+T` | Toggle Todo Panel visibility |

### Slash Commands

| Command | Description |
|---------|-------------|
| `/clear` | Reset conversation context |
| `/tokens` | Show current token count |
| `/tools` | List available tools |
| `exit` or `quit` | Exit the application |

## Session Management

### Starting a New Session

Each session receives a unique UUID for tracking. Sessions are stored in `~/.capybara/` directory.

```bash
capybara
```

### Resuming Previous Sessions

List and resume previous conversations:

```bash
capybara sessions  # List recent sessions
capybara resume <session_id>  # Resume specific session
```

### History

Command history is persisted in `~/.capybara/history` and available across sessions.

## Configuration

### Web UI Initialization

The recommended way to configure providers:

```bash
capybara init
```

This opens a local web server with a configuration UI in your browser. For terminal-only environments:

```bash
capybara init --cli
```

### Model Selection

Interactive model selection with available models from configured providers:

```bash
capybara model  # Interactive selection
capybara model <model_name>  # Set directly
```

### Configuration File

Settings are stored in `~/.capybara/config.yaml`:

```yaml
providers:
  - name: OpenAI
    api_type: openai
    model: gpt-4o
    api_key: sk-...
    rpm: 3500
    tpm: 90000
    max_tokens: 8000

memory:
  max_tokens: 100000
  persist: true

tools:
  bash_enabled: true
  bash_timeout: 120
```

## Running Single Prompts

For scripting or one-off queries:

```bash
capybara run "Explain the main function in src/main.py"
capybara run --no-stream "Generate unit tests"  # Disable streaming
capybara run --mode safe "Refactor this file"   # With mode
```

## Architecture

The CLI is built on:

- **Click**: Command-line argument parsing and command groups
- **Rich**: Beautiful terminal UI (panels, tables, syntax highlighting)
- **prompt_toolkit**: Interactive prompt with history and keybindings
- **asyncio**: Async operations for non-blocking I/O

Source files:
- `src/capybara/cli/main.py` - Command definitions
- `src/capybara/cli/interactive.py` - Interactive chat implementation
- `src/capybara/ui/` - UI components (panels, renderers)
