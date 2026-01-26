"""Settings screen for configuring the agent runner."""

from pathlib import Path

from opensymbolicai.llm import list_providers
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    DirectoryTree,
    Footer,
    Header,
    Label,
    Select,
    Static,
)

from opensymbolicai_cli.model_cache import fetch_models_for_provider
from opensymbolicai_cli.models import Settings

# Type alias for Select options
SelectOption = tuple[str, str]


class SettingsScreen(Screen[Settings | None]):
    """Screen for configuring application settings."""

    CSS = """
    SettingsScreen {
        layout: vertical;
    }

    #settings-container {
        width: 100%;
        height: 1fr;
        padding: 1 2;
    }

    .section-title {
        text-style: bold;
        color: $accent;
        margin: 1 0;
    }

    .section {
        height: auto;
        margin-bottom: 1;
        padding: 1;
        border: solid $surface;
        width: 100%;
    }

    #folder-row {
        height: 3;
        width: 100%;
    }

    #folder-row Label {
        width: 16;
        height: 3;
        content-align: left middle;
    }

    #current-folder {
        width: 1fr;
        height: 3;
        padding: 0 1;
        color: $success;
        background: $surface;
        content-align: left middle;
    }

    #browse-btn {
        margin-left: 1;
    }

    #folder-tree-container {
        height: 20;
        margin-top: 1;
    }

    #folder-tree {
        height: 100%;
    }

    #provider-section {
        height: auto;
    }

    .form-row {
        height: 3;
        margin: 1 0;
        width: 100%;
    }

    .form-row Label {
        width: 16;
        height: 3;
        content-align: left middle;
    }

    .form-row Select {
        width: 1fr;
    }

    #button-row {
        height: 3;
        margin-top: 1;
        align: center middle;
    }

    #button-row Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+s", "save", "Save"),
    ]

    def __init__(
        self,
        settings: Settings | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.settings = settings or Settings()
        self._selected_folder: Path | None = self.settings.agents_folder

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="settings-container"):
            yield Static("Settings", classes="section-title")

            with Vertical(id="folder-section", classes="section"):
                with Horizontal(id="folder-row"):
                    yield Label("Agents Folder:")
                    current = (
                        str(self.settings.agents_folder)
                        if self.settings.agents_folder
                        else "Not set"
                    )
                    yield Static(current, id="current-folder")
                    yield Button("Browse", id="browse-btn")
                with Container(id="folder-tree-container"):
                    yield DirectoryTree(Path.home(), id="folder-tree")

            with Vertical(id="provider-section", classes="section"):
                yield Label("Inference Settings:")
                with Horizontal(classes="form-row"):
                    yield Label("Provider:")
                    yield Select(
                        [(p, p) for p in list_providers()],
                        value=self.settings.default_provider,
                        id="provider-select",
                    )
                with Horizontal(classes="form-row"):
                    yield Label("Model:")
                    yield Select[str](
                        [("Loading...", "")],
                        value="",
                        id="model-select",
                    )

            with Horizontal(id="button-row"):
                yield Button("Save", variant="primary", id="save-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

        yield Footer()

    def on_mount(self) -> None:
        """Load models when screen mounts."""
        # Hide folder tree initially
        self.query_one("#folder-tree-container").display = False
        # Load models
        provider = self.settings.default_provider
        self._load_models_for_provider(provider)

    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        """Handle folder selection."""
        self._selected_folder = event.path
        current_folder = self.query_one("#current-folder", Static)
        current_folder.update(str(event.path))
        # Hide the tree after selection
        self.query_one("#folder-tree-container").display = False
        browse_btn = self.query_one("#browse-btn", Button)
        browse_btn.label = "Browse"

    @on(Select.Changed, "#provider-select")
    def on_provider_changed(self, event: Select.Changed) -> None:
        """Handle provider selection changes."""
        if event.value != Select.BLANK:
            self._load_models_for_provider(str(event.value))

    @work(exclusive=True, thread=True)
    def _load_models_for_provider(self, provider: str) -> None:
        """Load available models for the selected provider."""
        import asyncio

        self._set_model_options([("Loading...", "loading")])

        try:
            # Run the async fetch in the thread
            models = asyncio.run(fetch_models_for_provider(provider))
            if models:
                options: list[SelectOption] = [(m, m) for m in models]
                self.app.call_from_thread(self._set_model_options, options)
                # Set the value after options are set
                if self.settings.default_model in models:
                    self.app.call_from_thread(self._set_model_value, self.settings.default_model)
                else:
                    self.app.call_from_thread(self._set_model_value, models[0])
            else:
                self.app.call_from_thread(self._set_model_options, [("No models available", "")])
        except ValueError as e:
            # API key not set
            error_msg = str(e)
            self.app.call_from_thread(self._set_model_options, [(f"Error: {error_msg}", "")])
            self.app.call_from_thread(
                self.notify, f"Set {error_msg.upper()} environment variable", severity="error"
            )
        except Exception as e:
            self.app.call_from_thread(self._set_model_options, [(f"Error: {e}", "")])
            self.app.call_from_thread(self.notify, f"Error loading models: {e}", severity="error")

    def _set_model_options(self, options: list[SelectOption]) -> None:
        """Set model select options (must be called from main thread)."""
        model_select = self.query_one("#model-select", Select)
        model_select.set_options(options)

    def _set_model_value(self, value: str) -> None:
        """Set model select value (must be called from main thread)."""
        model_select = self.query_one("#model-select", Select)
        model_select.value = value

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "save-btn":
            self.action_save()
        elif event.button.id == "cancel-btn":
            self.action_cancel()
        elif event.button.id == "browse-btn":
            self._toggle_folder_tree()

    def _toggle_folder_tree(self) -> None:
        """Toggle folder tree visibility."""
        container = self.query_one("#folder-tree-container")
        browse_btn = self.query_one("#browse-btn", Button)
        container.display = not container.display
        browse_btn.label = "Hide" if container.display else "Browse"

    def action_save(self) -> None:
        """Save settings and dismiss screen."""
        provider_select = self.query_one("#provider-select", Select)
        model_select = self.query_one("#model-select", Select)

        provider = str(provider_select.value) if provider_select.value != Select.BLANK else "ollama"
        model = str(model_select.value) if model_select.value != Select.BLANK else ""

        settings = Settings(
            agents_folder=self._selected_folder,
            default_provider=provider,
            default_model=model,
        )
        self.dismiss(settings)

    def action_cancel(self) -> None:
        """Cancel and dismiss screen."""
        self.dismiss(None)
