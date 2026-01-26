"""Agent execution screen for running queries against an agent."""

from __future__ import annotations

import importlib.util
import sys
import threading
from typing import TYPE_CHECKING, Any

from opensymbolicai.models import MutationHookContext, OrchestrationResult
from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Footer, Header, Input, Static

if TYPE_CHECKING:
    from opensymbolicai_cli.models import Settings
    from opensymbolicai_cli.scanner import DiscoveredAgent


class MutationConfirmScreen(ModalScreen[bool]):
    """Modal dialog to confirm or abort a mutation operation."""

    CSS = """
    MutationConfirmScreen {
        align: center middle;
    }

    #mutation-dialog {
        width: 60;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $warning;
    }

    #mutation-title {
        text-style: bold;
        color: $warning;
        text-align: center;
        margin-bottom: 1;
    }

    #mutation-details {
        height: auto;
        padding: 1;
        margin-bottom: 1;
        background: $surface-darken-1;
        border-left: thick $accent;
    }

    #mutation-method {
        color: $success;
        text-style: bold;
    }

    #mutation-args {
        color: $text-muted;
        margin-top: 1;
    }

    #mutation-buttons {
        height: 3;
        align: center middle;
    }

    #mutation-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("enter", "continue", "Continue"),
        Binding("escape", "abort", "Abort"),
    ]

    def __init__(
        self,
        context: MutationHookContext,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.context = context

    def compose(self) -> ComposeResult:
        with Vertical(id="mutation-dialog"):
            yield Static("⚠️  Mutation Detected", id="mutation-title")
            with Vertical(id="mutation-details"):
                yield Static(f"Method: {self.context.method_name}()", id="mutation-method")
                args_str = ", ".join(f"{k}={v!r}" for k, v in self.context.args.items())
                if args_str:
                    yield Static(f"Args: {args_str}", id="mutation-args")
                else:
                    yield Static("Args: (none)", id="mutation-args")
            with Horizontal(id="mutation-buttons"):
                yield Button("Continue", variant="success", id="continue-btn")
                yield Button("Abort", variant="error", id="abort-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "continue-btn":
            self.action_continue()
        elif event.button.id == "abort-btn":
            self.action_abort()

    def action_continue(self) -> None:
        """Allow the mutation to proceed."""
        self.dismiss(True)

    def action_abort(self) -> None:
        """Abort the mutation."""
        self.dismiss(False)


class TracePanel(VerticalScroll):
    """Side panel for displaying execution trace."""

    DEFAULT_CSS = """
    TracePanel {
        width: 50;
        height: 100%;
        border-left: solid $secondary;
        background: $surface;
        padding: 1;
        display: none;
    }

    TracePanel.visible {
        display: block;
    }

    TracePanel .trace-header {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    TracePanel #trace-content {
        height: auto;
    }

    TracePanel .trace-step {
        margin-bottom: 1;
        padding: 1;
        background: $surface-darken-1;
        border-left: thick $accent;
    }

    TracePanel .trace-step.failed {
        border-left: thick $error;
        background: $error 10%;
    }

    TracePanel .step-header {
        color: $text;
        text-style: bold;
    }

    TracePanel .step-statement {
        color: $success;
        margin-top: 0;
    }

    TracePanel .step-result {
        color: $text-muted;
        margin-top: 0;
    }

    TracePanel .step-time {
        color: $text-disabled;
    }

    TracePanel .no-trace {
        color: $text-muted;
        text-style: italic;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("[bold]Execution Trace[/bold]", classes="trace-header")
        yield Vertical(id="trace-content")

    def update_trace(self, result: OrchestrationResult | None) -> None:
        """Update the trace panel with execution trace from the result."""
        content = self.query_one("#trace-content", Vertical)
        content.remove_children()

        if result is None or result.trace is None:
            content.mount(
                Static("[dim]No trace available. Run a query first.[/dim]", classes="no-trace")
            )
            return

        trace = result.trace
        for step in trace.steps:
            step_class = "trace-step" if step.success else "trace-step failed"

            # Build step content as rich text
            header_text = f"[bold]Step {step.step_number}[/bold]"
            if step.primitive_called:
                header_text += f" - {step.primitive_called}()"

            # Statement
            statement = step.statement
            if len(statement) > 60:
                statement = statement[:57] + "..."

            # Result
            if step.success:
                result_str = str(step.result_value)
                if len(result_str) > 50:
                    result_str = result_str[:47] + "..."
                result_line = f"→ {result_str}"
            else:
                result_line = f"[red]✗ {step.error}[/]"

            # Combine into single content block
            step_content = f"{header_text}\n[green]{statement}[/]\n{result_line}\n[dim]{step.time_seconds:.3f}s[/]"
            content.mount(Static(step_content, classes=step_class))

        # Total time
        content.mount(Static(f"\n[bold]Total: {trace.total_time_seconds:.3f}s[/bold]"))


class MessageDisplay(Static):
    """A single message in the conversation."""

    DEFAULT_CSS = """
    MessageDisplay {
        width: 100%;
        padding: 1;
        margin-bottom: 1;
    }

    MessageDisplay.user-message {
        background: $primary-darken-2;
        border-left: thick $primary;
    }

    MessageDisplay.assistant-message {
        background: $surface;
        border-left: thick $success;
    }

    MessageDisplay.error-message {
        background: $error 20%;
        border-left: thick $error;
    }

    MessageDisplay.system-message {
        background: $surface;
        border-left: thick $warning;
        color: $text-muted;
    }
    """


class ConversationView(VerticalScroll):
    """Scrollable container for conversation messages."""

    DEFAULT_CSS = """
    ConversationView {
        height: 1fr;
        border: solid $secondary;
        padding: 1;
    }

    ConversationView > #conversation-content {
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        yield Vertical(id="conversation-content")

    def add_message(self, content: str | Text | Syntax, message_type: str = "assistant") -> None:
        """Add a message to the conversation.

        Args:
            content: The message content (string, Rich Text, or Syntax).
            message_type: One of "user", "assistant", "error", "system".
        """
        conversation = self.query_one("#conversation-content", Vertical)
        message = MessageDisplay(content, classes=f"{message_type}-message")
        conversation.mount(message)
        self.scroll_end(animate=False)

    def clear_messages(self) -> None:
        """Clear all messages from the conversation."""
        conversation = self.query_one("#conversation-content", Vertical)
        conversation.remove_children()


class QueryInput(Static):
    """Input area for queries."""

    DEFAULT_CSS = """
    QueryInput {
        height: auto;
        padding: 1;
        border: solid $primary;
    }

    QueryInput > Static {
        margin-bottom: 1;
    }

    QueryInput > Input {
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("[bold]Enter your query:[/bold]")
        yield Input(placeholder="Type your query and press Enter...", id="query-input")


class AgentExecutionScreen(Screen[None]):
    """Screen for executing queries against an agent."""

    CSS = """
    AgentExecutionScreen {
        layout: vertical;
    }

    #agent-header {
        height: auto;
        padding: 1;
        background: $surface;
        border-bottom: solid $primary;
    }

    #agent-info {
        color: $text-muted;
    }

    #main-container {
        height: 1fr;
    }

    #execution-area {
        height: 1fr;
        padding: 1;
    }

    .status-bar {
        height: auto;
        padding: 0 1;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("ctrl+l", "clear", "Clear"),
        Binding("ctrl+t", "toggle_trace", "Trace"),
    ]

    def __init__(
        self,
        agent: DiscoveredAgent,
        settings: Settings,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.agent = agent
        self.settings = settings
        self.agent_instance: Any = None
        self.show_plan = False
        self._loading = False
        self.last_result: OrchestrationResult | None = None
        # Mutation approval state
        self._mutation_event: threading.Event | None = None
        self._mutation_approved: bool = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="agent-header")
        yield Horizontal(
            Vertical(
                ConversationView(id="conversation"),
                QueryInput(),
                Static("", id="status-bar", classes="status-bar"),
                id="execution-area",
            ),
            TracePanel(id="trace-panel"),
            id="main-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the screen."""
        self.title = f"Run: {self.agent.name}"

        # Update agent header
        header = self.query_one("#agent-header", Static)
        header_content = f"[bold]{self.agent.name}[/bold]"
        if self.agent.description:
            header_content += f"\n[dim]{self.agent.description}[/dim]"
        header.update(header_content)

        # Show welcome message
        conversation = self.query_one("#conversation", ConversationView)
        conversation.add_message(
            f"Agent [bold]{self.agent.name}[/bold] loaded. Type your query below.",
            "system",
        )

        # Update status
        self._update_status()

        # Focus the input
        self.query_one("#query-input", Input).focus()

        # Try to load the agent
        self._load_agent()

    def _update_status(self) -> None:
        """Update the status bar."""
        status = self.query_one("#status-bar", Static)
        provider = self.settings.default_provider or "not set"
        model = self.settings.default_model or "not set"
        plan_indicator = "[bold green]ON[/]" if self.show_plan else "[dim]OFF[/]"
        debug_indicator = "[bold green]ON[/]" if self.settings.debug_mode else "[dim]OFF[/]"
        trace_panel = self.query_one("#trace-panel", TracePanel)
        trace_indicator = "[bold green]ON[/]" if trace_panel.has_class("visible") else "[dim]OFF[/]"
        status.update(
            f"Provider: {provider} | Model: {model} | Plan: {plan_indicator} | Debug: {debug_indicator} | Trace: {trace_indicator}"
        )

    def _handle_mutation(self, context: MutationHookContext) -> str | None:
        """Handle mutation hook - called from execution thread.

        Shows a confirmation dialog and blocks until user responds.
        Returns None to allow mutation, or a rejection reason string.
        """
        # Create an event to wait for UI response
        self._mutation_event = threading.Event()
        self._mutation_approved = False

        # Schedule dialog on main thread
        self.app.call_from_thread(self._show_mutation_dialog, context)

        # Block until user responds
        self._mutation_event.wait()

        if self._mutation_approved:
            return None  # Allow mutation
        return "User aborted the mutation"

    def _show_mutation_dialog(self, context: MutationHookContext) -> None:
        """Show the mutation confirmation dialog (called on main thread)."""
        self.app.push_screen(MutationConfirmScreen(context), self._on_mutation_response)

    def _on_mutation_response(self, approved: bool | None) -> None:
        """Handle mutation dialog response."""
        self._mutation_approved = approved is True  # Treat None/False as rejection
        if self._mutation_event:
            self._mutation_event.set()

    def _load_agent(self) -> None:
        """Dynamically load and instantiate the agent."""
        conversation = self.query_one("#conversation", ConversationView)

        # Check if provider and model are configured
        if not self.settings.default_provider or not self.settings.default_model:
            conversation.add_message(
                "Provider or model not configured. Press 's' in main screen to configure settings.",
                "error",
            )
            return

        try:
            # Import the agent module dynamically
            file_path = self.agent.file_path
            module_name = file_path.stem

            # Add parent directory to path if needed
            parent_dir = str(file_path.parent)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)

            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                conversation.add_message(f"Could not load module from {file_path}", "error")
                return

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Get the agent class
            agent_class = getattr(module, self.agent.class_name, None)
            if agent_class is None:
                conversation.add_message(
                    f"Could not find class {self.agent.class_name} in module", "error"
                )
                return

            # Create LLM config
            from opensymbolicai.llm import LLMConfig

            llm_config = LLMConfig(
                provider=self.settings.default_provider,
                model=self.settings.default_model,
            )

            # Instantiate the agent
            self.agent_instance = agent_class(llm=llm_config)

            # Set mutation hook on the agent's config
            self.agent_instance.config.on_mutation = self._handle_mutation

            conversation.add_message(
                f"Agent initialized with {self.settings.default_provider}/{self.settings.default_model}",
                "system",
            )

        except Exception as e:
            conversation.add_message(f"Failed to load agent: {e}", "error")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle query submission."""
        if event.input.id != "query-input":
            return

        query = event.value.strip()
        if not query:
            return

        # Handle /plan command
        if query.lower() == "/plan":
            event.input.value = ""
            self._toggle_plan()
            return

        # Handle /debug command
        if query.lower() == "/debug":
            event.input.value = ""
            self._toggle_debug_mode()
            return

        # Handle /trace command
        if query.lower() == "/trace":
            event.input.value = ""
            self.action_toggle_trace()
            return

        conversation = self.query_one("#conversation", ConversationView)

        # Show user query immediately
        conversation.add_message(f"[bold]You:[/bold] {query}", "user")

        # Clear input after showing message
        event.input.value = ""

        # Check if agent is loaded
        if self.agent_instance is None:
            conversation.add_message("Agent not loaded. Check settings and try again.", "error")
            return

        # Prevent concurrent executions
        if self._loading:
            return
        self._loading = True

        # Run in background worker so UI updates immediately
        self.run_worker(self._execute_query(query), exclusive=True)

    def _toggle_debug_mode(self) -> None:
        """Toggle debug mode on/off."""
        self.settings.debug_mode = not self.settings.debug_mode
        self.settings.save()
        self._update_status()
        mode = "enabled" if self.settings.debug_mode else "disabled"
        self.notify(f"Debug mode {mode}")

    async def _execute_query(self, query: str) -> None:
        """Execute a query against the agent."""
        conversation = self.query_one("#conversation", ConversationView)

        # Update status to show processing
        status = self.query_one("#status-bar", Static)
        status.update("[yellow]Processing...[/]")

        try:
            # Run the agent in a thread pool to avoid blocking the UI
            result: OrchestrationResult = await self._run_in_thread(
                lambda: self.agent_instance.run(query)
            )

            # Store the result for trace panel
            self.last_result = result

            # Update trace panel if visible
            trace_panel = self.query_one("#trace-panel", TracePanel)
            if trace_panel.has_class("visible"):
                trace_panel.update_trace(result)

            # Show plan output if enabled
            if self.show_plan and result.plan_attempts:
                for i, attempt in enumerate(result.plan_attempts):
                    plan_code = (
                        attempt.plan_generation.extracted_code if attempt.plan_generation else ""
                    )
                    if plan_code:
                        conversation.add_message(f"[dim]--- Plan Attempt {i + 1} ---[/]", "system")
                        syntax = Syntax(plan_code, "python", theme="monokai", line_numbers=False)
                        conversation.add_message(syntax, "system")

            # Show debug info if enabled
            if self.settings.debug_mode:
                self._show_debug_info(conversation, result)

            # Show result
            if result.success:
                conversation.add_message(
                    f"[bold green]Result:[/bold green] {result.result}", "assistant"
                )
            else:
                error_msg = f"[bold red]Error:[/bold red] {result.error}"
                if result.plan:
                    error_msg += f"\n\n[dim]Plan attempted:[/dim]\n{result.plan}"
                conversation.add_message(error_msg, "error")

        except Exception as e:
            conversation.add_message(f"[bold red]Exception:[/bold red] {e}", "error")

        finally:
            # Restore status and reset loading flag
            self._loading = False
            self._update_status()

    def _show_debug_info(self, conversation: ConversationView, result: OrchestrationResult) -> None:
        """Display debug information about the execution."""
        debug_parts: list[str] = []

        # Time taken from metrics
        if result.metrics:
            metrics = result.metrics
            total_time = metrics.total_time_seconds
            debug_parts.append(
                f"[bold cyan]Time:[/] {total_time:.2f}s "
                f"(plan: {metrics.plan_time_seconds:.2f}s, exec: {metrics.execute_time_seconds:.2f}s)"
            )

            # Token usage
            tokens = metrics.plan_tokens
            total_tokens = tokens.total_tokens
            debug_parts.append(
                f"[bold cyan]Tokens:[/] {total_tokens} "
                f"(input: {tokens.input_tokens}, output: {tokens.output_tokens})"
            )

        # Plan
        if result.plan:
            debug_parts.append(f"[bold cyan]Plan:[/]\n{result.plan}")

        if debug_parts:
            debug_text = "[dim]--- Debug Info ---[/]\n" + "\n".join(debug_parts)
            conversation.add_message(debug_text, "system")

    async def _run_in_thread(self, func: Any) -> Any:
        """Run a blocking function in a thread pool."""
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            return await loop.run_in_executor(executor, func)

    def action_back(self) -> None:
        """Go back to main screen."""
        self.dismiss(None)

    def action_clear(self) -> None:
        """Clear the conversation."""
        conversation = self.query_one("#conversation", ConversationView)
        conversation.clear_messages()
        conversation.add_message(
            f"Agent [bold]{self.agent.name}[/bold] ready. Type your query below.",
            "system",
        )

    def _toggle_plan(self) -> None:
        """Toggle plan visibility."""
        self.show_plan = not self.show_plan
        self._update_status()
        mode = "shown" if self.show_plan else "hidden"
        self.notify(f"Plan {mode}")

    def action_toggle_trace(self) -> None:
        """Toggle trace panel visibility."""
        trace_panel = self.query_one("#trace-panel", TracePanel)
        if trace_panel.has_class("visible"):
            trace_panel.remove_class("visible")
            self.notify("Trace panel hidden")
        else:
            trace_panel.add_class("visible")
            trace_panel.update_trace(self.last_result)
            self.notify("Trace panel shown")
        self._update_status()
