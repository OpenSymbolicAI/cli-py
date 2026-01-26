"""Agent details screen showing methods and source code."""

import re

from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, ListItem, ListView, Static

from opensymbolicai_cli.scanner import DiscoveredAgent, DiscoveredMethod


def _parse_signature_parts(signature: str) -> tuple[list[str], str]:
    """Parse method signature to extract inputs and return type.

    Args:
        signature: Full method signature string.

    Returns:
        Tuple of (list of input parameters, return type string).
    """
    inputs: list[str] = []
    return_type = "None"

    # Extract return type
    if "->" in signature:
        return_match = re.search(r"->\s*(.+?):\s*$", signature, re.MULTILINE | re.DOTALL)
        if return_match:
            return_type = return_match.group(1).strip()

    # Extract parameters between parentheses
    paren_match = re.search(r"\((.*?)\)", signature, re.DOTALL)
    if paren_match:
        params_str = paren_match.group(1)
        # Split by comma, but handle nested brackets
        params = []
        depth = 0
        current = ""
        for char in params_str:
            if char in "([{":
                depth += 1
            elif char in ")]}":
                depth -= 1
            if char == "," and depth == 0:
                params.append(current.strip())
                current = ""
            else:
                current += char
        if current.strip():
            params.append(current.strip())

        for param in params:
            param = param.strip()
            # Skip self parameter
            if param == "self" or param.startswith("self,"):
                continue
            if not param:
                continue
            inputs.append(param)

    return inputs, return_type


class MethodListItem(ListItem):
    """A list item representing a method."""

    def __init__(self, method: DiscoveredMethod) -> None:
        super().__init__()
        self.method = method

    def compose(self) -> ComposeResult:
        # ● for primitives (atomic action), ↳ for decompositions (breaks down into sub-steps)
        type_icon = "●" if self.method.method_type == "primitive" else "↳"
        ro_marker = " [dim](ro)[/dim]" if self.method.read_only else ""
        yield Static(f"{type_icon} {self.method.name}{ro_marker}", classes="method-name")


class MethodList(Vertical):
    """Left panel showing list of methods with their signatures."""

    def compose(self) -> ComposeResult:
        yield Static("Methods", classes="panel-title")
        yield Static("[dim]● primitive  ↳ decomposition[/dim]", classes="legend")
        yield ListView(id="method-list")
        yield Static("", id="method-info")


class SourceViewer(VerticalScroll):
    """Right panel showing full method source code."""

    def compose(self) -> ComposeResult:
        yield Static("Source Code", classes="panel-title")
        yield Static("Select a method to view source", id="source-content", classes="source-code")


class AgentDetailsScreen(Screen[None]):
    """Screen showing detailed agent methods and source code."""

    CSS = """
    AgentDetailsScreen {
        layout: grid;
        grid-size: 2;
        grid-columns: 1fr 2fr;
    }

    MethodList {
        width: 100%;
        height: 100%;
        border: solid $primary;
        padding: 1;
    }

    SourceViewer {
        width: 100%;
        height: 100%;
        border: solid $secondary;
        padding: 1;
    }

    .panel-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    .legend {
        margin-bottom: 1;
    }

    #method-list {
        height: 1fr;
        margin-bottom: 1;
    }

    .method-name {
        padding: 0 1;
    }

    #method-info {
        height: auto;
        margin-top: 1;
        padding: 1;
        background: $surface;
    }

    #source-content {
        width: 100%;
    }

    .source-code {
        color: $text;
    }
    """

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("q", "back", "Back"),
    ]

    def __init__(
        self,
        agent: DiscoveredAgent,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.agent = agent

    def compose(self) -> ComposeResult:
        yield Header()
        yield MethodList()
        yield SourceViewer()
        yield Footer()

    def on_mount(self) -> None:
        """Populate method list on mount."""
        method_list = self.query_one("#method-list", ListView)

        # Group methods by type
        primitives = [m for m in self.agent.methods if m.method_type == "primitive"]
        decompositions = [m for m in self.agent.methods if m.method_type == "decomposition"]

        # Add primitives first
        for method in primitives:
            method_list.append(MethodListItem(method))

        # Add decompositions
        for method in decompositions:
            method_list.append(MethodListItem(method))

        # Auto-select first method if available
        if self.agent.methods:
            method_list.index = 0
            first_method = primitives[0] if primitives else decompositions[0]
            self._show_method(first_method)

        # Update header
        self.title = f"Agent: {self.agent.name}"

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Handle cursor movement in the method list."""
        if isinstance(event.item, MethodListItem):
            self._show_method(event.item.method)

    def _show_method(self, method: DiscoveredMethod) -> None:
        """Display method details in both panels."""
        # Update method info panel (left side, below list)
        self._update_method_info(method)

        # Update source viewer (right side)
        self._update_source_viewer(method)

    def _update_method_info(self, method: DiscoveredMethod) -> None:
        """Update the method info section below the method list."""
        method_info = self.query_one("#method-info", Static)

        inputs, return_type = _parse_signature_parts(method.signature)

        lines = []
        lines.append(f"[bold]{method.name}[/bold]")
        lines.append(f"Type: {method.method_type}")

        if method.method_type == "primitive":
            lines.append(f"Read-only: {'Yes' if method.read_only else 'No'}")
        elif method.intent:
            lines.append(f"Intent: {method.intent}")

        lines.append("")
        lines.append("[bold]Inputs:[/bold]")
        if inputs:
            for inp in inputs:
                lines.append(f"  • {inp}")
        else:
            lines.append("  [dim](none)[/dim]")

        lines.append("")
        lines.append(f"[bold]Returns:[/bold] {return_type}")

        method_info.update("\n".join(lines))

    def _update_source_viewer(self, method: DiscoveredMethod) -> None:
        """Update the source code viewer with syntax highlighting."""
        source_content = self.query_one("#source-content", Static)

        if not method.source:
            source_content.update(Text("Source code not available", style="dim"))
            return

        # Use rich Syntax for Python syntax highlighting
        syntax = Syntax(
            method.source,
            "python",
            theme="monokai",
            line_numbers=True,
            word_wrap=False,
        )
        source_content.update(syntax)

    def action_back(self) -> None:
        """Go back to main screen."""
        self.dismiss(None)
