"""Main Textual application for Agent Runner."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Footer, Header, ListItem, ListView, Static

from opensymbolicai_cli.models import Settings
from opensymbolicai_cli.scanner import DiscoveredAgent, scan_directory_for_agents
from opensymbolicai_cli.screens.agent_details import AgentDetailsScreen
from opensymbolicai_cli.screens.agent_execution import AgentExecutionScreen
from opensymbolicai_cli.screens.settings import SettingsScreen


class AgentListItem(ListItem):
    """A list item representing an agent."""

    def __init__(self, agent: DiscoveredAgent) -> None:
        super().__init__()
        self.agent = agent

    def compose(self) -> ComposeResult:
        yield Static(self.agent.name, classes="agent-name")


class Sidebar(Static):
    """Sidebar widget for agent list."""

    def compose(self) -> ComposeResult:
        yield Static("Agents", classes="sidebar-title")
        yield ListView(id="agent-list")


class AgentDetails(VerticalScroll):
    """Widget showing details of the selected agent."""

    def compose(self) -> ComposeResult:
        yield Vertical(id="agent-details-content")

    def show_agent(self, agent: DiscoveredAgent) -> None:
        """Display high-level agent information."""
        content = self.query_one("#agent-details-content", Vertical)
        content.remove_children()

        # Agent name
        content.mount(Static(f"[bold]{agent.name}[/bold]", classes="detail-title"))

        # Description
        if agent.description:
            content.mount(Static(agent.description, classes="detail-text"))
            content.mount(Static(""))

        # High-level metadata
        content.mount(Static(f"Class: [bold]{agent.class_name}[/bold]"))
        content.mount(Static(f"Base: {agent.base_class}"))
        if agent.version:
            content.mount(Static(f"Version: {agent.version}"))
        content.mount(Static(f"File: {agent.file_path.name}"))

        # Methods summary
        primitives = [m for m in agent.methods if m.method_type == "primitive"]
        decompositions = [m for m in agent.methods if m.method_type == "decomposition"]
        read_only_count = sum(1 for m in primitives if m.read_only)
        mutable_count = len(primitives) - read_only_count

        content.mount(Static(""))
        content.mount(Static("[bold]Capabilities[/bold]", classes="detail-section"))
        content.mount(Static(f"  Primitives: {len(primitives)}"))
        if primitives:
            content.mount(Static(f"    Read-only: {read_only_count}"))
            content.mount(Static(f"    Mutable: {mutable_count}"))
        content.mount(Static(f"  Decompositions: {len(decompositions)}"))

    def show_placeholder(self) -> None:
        """Show placeholder when no agent is selected."""
        content = self.query_one("#agent-details-content", Vertical)
        content.remove_children()
        content.mount(Static("Select an agent to view details", classes="placeholder"))


class MainContent(Static):
    """Main content area for agent details."""

    def compose(self) -> ComposeResult:
        yield Static("Agent Details", classes="content-title")
        yield AgentDetails(id="agent-details")


class AgentRunnerApp(App[None]):
    """A TUI for discovering and running agents."""

    TITLE = "OpenSymbolicAI Agent Runner"
    CSS = """
    Screen {
        layout: grid;
        grid-size: 2;
        grid-columns: 1fr 3fr;
    }

    Sidebar {
        width: 100%;
        height: 100%;
        border: solid $primary;
        padding: 1;
    }

    .sidebar-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #agent-list {
        height: 1fr;
    }

    .agent-name {
        padding: 0 1;
    }

    MainContent {
        width: 100%;
        height: 100%;
        border: solid $secondary;
        padding: 1;
    }

    .content-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #agent-details {
        height: 1fr;
    }

    .detail-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    .detail-section {
        color: $accent;
        margin-top: 1;
    }

    .detail-text {
        color: $text-muted;
    }

    .placeholder {
        color: $text-muted;
        text-style: italic;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("d", "details", "Details"),
        Binding("s", "settings", "Settings"),
        Binding("r", "refresh", "Refresh"),
        Binding("?", "help", "Help"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.settings = Settings.load()
        self.agents: list[DiscoveredAgent] = []
        self.selected_agent: DiscoveredAgent | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Sidebar()
        yield MainContent()
        yield Footer()

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        self._scan_agents()

    def _scan_agents(self) -> None:
        """Scan for agents in the configured folder."""
        agent_list = self.query_one("#agent-list", ListView)
        details = self.query_one("#agent-details", AgentDetails)
        agent_list.clear()

        if not self.settings.agents_folder:
            details.show_placeholder()
            self.notify("No agents folder configured. Press 's' to set one.")
            return

        if not self.settings.agents_folder.exists():
            details.show_placeholder()
            self.notify(f"Agents folder not found: {self.settings.agents_folder}")
            return

        self.agents = scan_directory_for_agents(self.settings.agents_folder)

        if not self.agents:
            details.show_placeholder()
            self.notify("No agents found in the configured folder.")
            return

        for agent in self.agents:
            agent_list.append(AgentListItem(agent))

        # Auto-select the first agent
        agent_list.index = 0
        self.selected_agent = self.agents[0]
        details.show_agent(self.agents[0])

        self.notify(f"Found {len(self.agents)} agent(s)")

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Handle cursor movement in the agent list."""
        if isinstance(event.item, AgentListItem):
            self.selected_agent = event.item.agent
            details = self.query_one("#agent-details", AgentDetails)
            details.show_agent(event.item.agent)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle agent selection from the list - opens execution screen."""
        if isinstance(event.item, AgentListItem):
            self.selected_agent = event.item.agent
            # Open execution screen when Enter is pressed
            self.push_screen(AgentExecutionScreen(event.item.agent, self.settings))

    def action_settings(self) -> None:
        """Open the settings screen."""
        self.push_screen(SettingsScreen(self.settings), self._on_settings_closed)

    def _on_settings_closed(self, settings: Settings | None) -> None:
        """Handle settings screen closing."""
        if settings is not None:
            self.settings = settings
            settings.save()
            self.notify(f"Settings saved: {settings.default_provider}/{settings.default_model}")
            # Rescan agents with new folder
            self._scan_agents()

    def action_refresh(self) -> None:
        """Refresh the agent list."""
        self._scan_agents()

    def action_help(self) -> None:
        """Show help."""
        self.notify("Help: q=quit, d=details, s=settings, r=refresh, ?=help")

    def action_details(self) -> None:
        """Open the agent details screen."""
        if self.selected_agent is None:
            self.notify("No agent selected")
            return
        if not self.selected_agent.methods:
            self.notify("No methods found for this agent")
            return
        self.push_screen(AgentDetailsScreen(self.selected_agent))
