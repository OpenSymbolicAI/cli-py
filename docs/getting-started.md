# Getting Started

## Installation

=== "uv (recommended)"

    ```bash
    uv add opensymbolicai-cli
    ```

=== "pip"

    ```bash
    pip install opensymbolicai-cli
    ```

## Requirements

- Python 3.12 or higher
- [opensymbolicai-core](https://github.com/OpenSymbolicAI/core-py) (installed automatically)

## Basic Usage

### Running the CLI

Launch the interactive TUI:

```bash
opensymbolicai
```

### Environment Configuration

Create a `.env` file in your project root to configure API keys and settings:

```bash
OPENAI_API_KEY=your-api-key
ANTHROPIC_API_KEY=your-api-key
```

## Navigation

The TUI supports keyboard navigation:

- **Arrow keys**: Navigate between items
- **Enter**: Select/confirm
- **Escape**: Go back/cancel
- **q**: Quit the application
