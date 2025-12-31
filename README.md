# Capybara Vibe

**Async-first AI-powered CLI coding assistant implementing the ReAct agent pattern.**

Capybara Vibe is a powerful command-line interface designed to assist developers by leveraging Large Language Models (LLMs) to understand, plan, and execute coding tasks directly within your terminal. It supports interactive chat, one-off command execution, and session management, all built on a robust async architecture.

## Features

- **ReAct Agent Pattern**: Implements sophisticated reasoning and acting loops to solve complex problems.
- **Interactive Chat**: Natural language conversation with context awareness.
- **Multi-Mode Operation**:
  - `standard`: Balanced autonomy and safety.
  - `safe`: Restricted permissions, asking for confirmation before critical actions.
  - `plan`: Focuses on planning without execution permissions.
  - `auto`: High autonomy for trusted tasks.
- **Session Management**: Save, list, and resume conversation sessions.
- **Model Flexibility**: Easy switching between different LLM providers and models.
- **Configuration UI**: Built-in Web UI for easy configuration management.
- **MCP Support**: Model Context Protocol (MCP) enabled for enhanced context integration.

## Installation

Ensure you have Python 3.10 or higher installed.

```bash
pip install capybara-vibe
```

## Getting Started

### 1. Configuration

Before using Capybara, you need to initialize the configuration. You can do this via an interactive Web UI or through the CLI.

**Web UI (Recommended):**
```bash
capybara init
```
This will open a configuration page in your browser where you can set up your LLM providers (e.g., OpenAI, Anthropic) and other settings.

**CLI Only:**
```bash
capybara init --cli
```

### 2. Basic Usage

**Interactive Chat:**
Start a new chat session to brainstorm or ask questions.
```bash
capybara chat
```
You can also start with an initial message:
```bash
capybara chat "Refactor the authentication middleware in src/"
```

**Single Command Run:**
Execute a specific task and exit.
```bash
capybara run "Write a unit test for the user login function"
```

### 3. Usage Options

**Select Model:**
Specify a model for a specific command:
```bash
capybara chat --model gpt-4-turbo
```

**Set Default Model:**
View available models and set a global default:
```bash
capybara model
```
Or set it directly:
```bash
capybara model gpt-4-turbo
```

**Modes:**
Run in different modes depending on your needs:
```bash
capybara chat --mode safe   # Asks for permission before file edits
capybara chat --mode plan   # Only generates plans, no file edits
```

### 4. Session Management

**List Sessions:**
See your recent activity.
```bash
capybara sessions
```

**Resume a Session:**
Pick up where you left off using the Session ID.
```bash
capybara resume <session_id>
```

## Development

To contribute to Capybara Vibe Coding:

1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install -e ".[dev]"
   ```
3. Run tests:
   ```bash
   pytest
   ```

## License

[MIT](LICENSE)
