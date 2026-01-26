# OpenSymbolicAI CLI

Interactive TUI for discovering and running OpenSymbolicAI agents.

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/OpenSymbolicAI/cli-py.git
cd cli-py
```

### 2. Set up a model provider

**Option A: Local with Ollama**

Install [Ollama](https://ollama.ai) and pull a model:

```bash
ollama pull qwen3
# or: ollama pull gemma3
# or: ollama pull gpt-oss:20b
```

**Option B: Cloud API**

Copy `.env.example` to `.env` and add your API key(s):

```bash
cp .env.example .env
```

```
FIREWORKS_API_KEY=your_key_here
GROQ_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
```

### 3. Launch the CLI

```bash
uv run opensymbolicai
```

## Usage

1. **Settings** - Set the directory where your agents live. Example: if you cloned [core-py](https://github.com/OpenSymbolicAI/core-py), point it to the examples folder:
   ```
   /path/to/core-py/examples/calculator
   ```

2. **Pick provider/model** - Select your default provider and model in settings.

3. **Run an agent** - Go back to the agents page, select an agent (e.g., `ScientificCalculator`), and ask away:
   ```
   What is the square root of 144 plus 3 factorial?
   ```

## Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

## License

MIT
