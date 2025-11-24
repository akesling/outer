#!/usr/bin/env python3
"""
Outer - Meta-workflow orchestrator for Claude Code planning sessions.

Automates the heavy-handed planning workflow:
1. outer plan "description" -> Design architecture
2. outer roadmap -> Create implementation roadmap
3. outer phases -> Generate detailed phase files
4. outer prompt -> Create universal resume prompt
5. outer install -> Install as slash command
6. outer run -> Execute with resume prompt
"""

import asyncio
import re
from pathlib import Path
from typing import Any

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Static,
)
from textual.screen import ModalScreen

from claude_code_sdk import (
    query,
    ClaudeCodeOptions,
    TextBlock,
    ToolUseBlock,
    ResultMessage,
    AssistantMessage,
)


# ============================================================================
# Utility Functions
# ============================================================================

def slugify(name: str) -> str:
    """Convert a name to a slug for filenames."""
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')


def find_planning_files(cwd: Path) -> dict[str, Path | None]:
    """Discover existing planning files in docs/."""
    docs = cwd / "docs"
    phases_dir = docs / "phases"

    result = {
        "architecture": None,
        "roadmap": None,
        "phase_index": None,
        "resume_prompt": None,
    }

    if not docs.exists():
        return result

    for f in docs.glob("*_ARCHITECTURE.md"):
        result["architecture"] = f
        break

    for f in docs.glob("*_ROADMAP.md"):
        result["roadmap"] = f
        break

    if phases_dir.exists():
        for f in phases_dir.glob("*_PHASE_INDEX.md"):
            result["phase_index"] = f
            break

    for f in docs.glob("*_RESUME_PROMPT.md"):
        result["resume_prompt"] = f
        break

    return result


def get_slug_from_files(files: dict[str, Path | None]) -> str | None:
    """Extract the project slug from existing files."""
    for key in ["architecture", "roadmap", "resume_prompt"]:
        if files[key]:
            name = files[key].stem
            for suffix in ["_ARCHITECTURE", "_ROADMAP", "_RESUME_PROMPT"]:
                if name.endswith(suffix):
                    return name[:-len(suffix)]
    if files["phase_index"]:
        name = files["phase_index"].stem
        if name.endswith("_PHASE_INDEX"):
            return name[:-len("_PHASE_INDEX")]
    return None


# ============================================================================
# Prompt Templates
# ============================================================================

PROMPTS = {
    "architecture": """Design and write a full architecture plan for: {description}

Create a comprehensive architecture document at docs/{slug}_ARCHITECTURE.md that includes:

1. **Overview**: High-level description and why this work is needed
2. **Goals & Non-Goals**: What we're trying to achieve and explicit boundaries
3. **System Architecture**: Components, responsibilities, interactions
4. **Data Flow**: How data moves through the system
5. **Key Technical Decisions**: Technology choices and rationale
6. **API/Interface Design**: Public interfaces and contracts
7. **Error Handling Strategy**: How errors are handled
8. **Testing Strategy**: Approach to testing
9. **Dependencies**: External dependencies needed
10. **Open Questions**: Unresolved decisions needing input

Be thorough and specific. This document drives implementation.""",

    "roadmap": """Given the architecture document at {arch_path}, write a complete implementation roadmap.

Create docs/{slug}_ROADMAP.md with:

1. **Implementation Phases**: Logical phases that build on each other
2. **Phase Dependencies**: What must complete before each phase
3. **Milestone Definitions**: Clear deliverables per phase
4. **Risk Assessment**: Technical risks and mitigations
5. **Integration Points**: Where phases connect
6. **Parallel Work**: What can be done concurrently

Each phase should be:
- Self-contained enough to verify independently
- Small enough to complete in a focused session
- Large enough to represent meaningful progress""",

    "phases": """Given the roadmap at {roadmap_path}, create detailed phase planning files.

For each phase, create docs/phases/{slug}_PHASE_N.md containing:

1. **Phase Overview**: What this phase accomplishes
2. **Prerequisites**: What must be true before starting
3. **Acceptance Criteria**: Testable conditions for completion (checkboxes)
4. **TODO System**: Granular task list with checkboxes
5. **Implementation Notes**: Technical guidance for Claude Code
   - Key files to create/modify
   - Patterns to follow
   - Gotchas to avoid
   - Testing requirements
6. **Verification Steps**: How to verify completion
7. **Handoff Notes**: What next phase needs to know

Also create docs/phases/{slug}_PHASE_INDEX.md listing all phases with status.""",

    "resume_prompt": """Given the roadmap at {roadmap_path} and phase files in docs/phases/, create a universal resume prompt.

Create docs/{slug}_RESUME_PROMPT.md containing a prompt that:

1. Works in ANY clean Claude Code session to resume work
2. Works identically regardless of current phase
3. Auto-detects progress by reading phase files
4. Immediately starts on next incomplete task
5. Updates checkboxes and status as work completes
6. Is resilient to session kills - progress saved to files

The prompt should:
- Read phase index to find current phase
- Read that phase file for next incomplete task
- Work until complete or blocked
- Update phase file with progress
- Be fully self-contained

Goal: paste into fresh Claude Code, work happens automatically.""",
}


# ============================================================================
# Modal Screens
# ============================================================================

class PlanInputScreen(ModalScreen[str | None]):
    """Modal screen for entering plan description."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="plan-dialog"):
            yield Label("Enter project description:", id="plan-label")
            yield Input(placeholder="e.g., Add user authentication with OAuth", id="plan-input")
            with Horizontal(id="plan-buttons"):
                yield Button("Start Planning", variant="primary", id="plan-submit")
                yield Button("Cancel", variant="default", id="plan-cancel")

    def on_mount(self) -> None:
        self.query_one("#plan-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "plan-submit":
            value = self.query_one("#plan-input", Input).value.strip()
            if value:
                self.dismiss(value)
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.value.strip():
            self.dismiss(event.value.strip())

    def action_cancel(self) -> None:
        self.dismiss(None)


# ============================================================================
# Main Application
# ============================================================================

class OuterApp(App):
    """Main TUI application for Outer workflow orchestration."""

    CSS = """
    #plan-dialog {
        width: 60;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }

    #plan-label {
        margin-bottom: 1;
    }

    #plan-input {
        margin-bottom: 1;
    }

    #plan-buttons {
        height: 3;
        align: center middle;
    }

    #plan-buttons Button {
        margin: 0 1;
    }

    #sidebar {
        width: 32;
        background: $surface;
        border-right: solid $primary;
        padding: 1;
    }

    #main {
        width: 1fr;
    }

    #output {
        height: 1fr;
        border: solid $primary;
        padding: 0 1;
    }

    #status-panel {
        height: auto;
        margin-bottom: 1;
    }

    #status-title {
        text-style: bold;
        margin-bottom: 1;
    }

    .status-item {
        height: 1;
    }

    .status-done {
        color: $success;
    }

    .status-pending {
        color: $text-muted;
    }

    #actions {
        height: auto;
        margin-top: 1;
    }

    #actions-title {
        text-style: bold;
        margin-bottom: 1;
    }

    #actions Button {
        width: 100%;
        margin-bottom: 1;
    }

    #info-panel {
        height: auto;
        margin-top: 1;
        padding-top: 1;
        border-top: solid $primary;
    }

    #info-title {
        text-style: bold;
        margin-bottom: 1;
    }

    .info-item {
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("1", "run_plan", "Plan"),
        Binding("2", "run_roadmap", "Roadmap"),
        Binding("3", "run_phases", "Phases"),
        Binding("4", "run_prompt", "Prompt"),
        Binding("5", "run_install", "Install"),
        Binding("6", "run_execute", "Run"),
        Binding("r", "refresh", "Refresh"),
        Binding("c", "clear_output", "Clear"),
    ]

    def __init__(self):
        super().__init__()
        self.cwd = Path.cwd()
        self.files: dict[str, Path | None] = {}
        self.slug: str | None = None
        self.running = False
        self.total_cost = 0.0
        self.total_turns = 0

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="sidebar"):
                with Vertical(id="status-panel"):
                    yield Static("Status", id="status-title")
                    yield Static("• Architecture", id="status-arch", classes="status-item status-pending")
                    yield Static("• Roadmap", id="status-road", classes="status-item status-pending")
                    yield Static("• Phases", id="status-phases", classes="status-item status-pending")
                    yield Static("• Prompt", id="status-prompt", classes="status-item status-pending")
                    yield Static("• Installed", id="status-install", classes="status-item status-pending")
                with Vertical(id="actions"):
                    yield Static("Actions", id="actions-title")
                    yield Button("1. Plan", id="btn-plan")
                    yield Button("2. Roadmap", id="btn-roadmap")
                    yield Button("3. Phases", id="btn-phases")
                    yield Button("4. Prompt", id="btn-prompt")
                    yield Button("5. Install", id="btn-install")
                    yield Button("6. Run", id="btn-run", variant="primary")
                with Vertical(id="info-panel"):
                    yield Static("Session", id="info-title")
                    yield Static("Cost: $0.0000", id="info-cost", classes="info-item")
                    yield Static("Turns: 0", id="info-turns", classes="info-item")
            with Vertical(id="main"):
                yield RichLog(id="output", highlight=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_status()
        self.log_message("[bold]Outer[/bold] - Claude Code Planning Workflow\n")
        self.log_message(f"Working directory: {self.cwd}\n")
        if self.slug:
            self.log_message(f"Project: [cyan]{self.slug}[/cyan]\n")
        else:
            self.log_message("No project found. Press [bold]1[/bold] to start planning.\n")

    def refresh_status(self) -> None:
        """Refresh the status display."""
        self.files = find_planning_files(self.cwd)
        self.slug = get_slug_from_files(self.files)

        # Update status indicators
        items = [
            ("status-arch", "architecture", "Architecture"),
            ("status-road", "roadmap", "Roadmap"),
            ("status-phases", "phase_index", "Phases"),
            ("status-prompt", "resume_prompt", "Prompt"),
        ]

        for widget_id, file_key, label in items:
            widget = self.query_one(f"#{widget_id}", Static)
            if self.files[file_key]:
                widget.update(f"[green]✓[/green] {label}")
                widget.remove_class("status-pending")
                widget.add_class("status-done")
            else:
                widget.update(f"• {label}")
                widget.remove_class("status-done")
                widget.add_class("status-pending")

        # Check slash command
        install_widget = self.query_one("#status-install", Static)
        if self.slug:
            cmd_file = self.cwd / ".claude" / "commands" / f"resume-{self.slug.replace('_', '-')}.md"
            if cmd_file.exists():
                install_widget.update("[green]✓[/green] Installed")
                install_widget.remove_class("status-pending")
                install_widget.add_class("status-done")
            else:
                install_widget.update("• Installed")
                install_widget.remove_class("status-done")
                install_widget.add_class("status-pending")

        # Update title
        title = self.slug or "No project"
        self.title = f"Outer - {title}"

    def log_message(self, message: str) -> None:
        """Write a message to the output log."""
        self.query_one("#output", RichLog).write(message)

    def update_info(self, cost: float, turns: int) -> None:
        """Update session info display."""
        self.total_cost += cost
        self.total_turns += turns
        self.query_one("#info-cost", Static).update(f"Cost: ${self.total_cost:.4f}")
        self.query_one("#info-turns", Static).update(f"Turns: {self.total_turns}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if self.running:
            self.log_message("[yellow]Session already running...[/yellow]\n")
            return

        actions = {
            "btn-plan": self.action_run_plan,
            "btn-roadmap": self.action_run_roadmap,
            "btn-phases": self.action_run_phases,
            "btn-prompt": self.action_run_prompt,
            "btn-install": self.action_run_install,
            "btn-run": self.action_run_execute,
        }
        action = actions.get(event.button.id)
        if action:
            action()

    def action_refresh(self) -> None:
        """Refresh status display."""
        self.refresh_status()
        self.log_message("[dim]Status refreshed[/dim]\n")

    def action_clear_output(self) -> None:
        """Clear the output log."""
        self.query_one("#output", RichLog).clear()

    def action_run_plan(self) -> None:
        """Start the planning phase."""
        if self.running:
            return

        def handle_result(result: str | None) -> None:
            if result:
                self.run_phase_plan(result)

        self.push_screen(PlanInputScreen(), handle_result)

    def action_run_roadmap(self) -> None:
        """Run the roadmap phase."""
        if self.running:
            return
        if not self.files["architecture"]:
            self.log_message("[red]No architecture file found. Run Plan first.[/red]\n")
            return
        self.run_phase_roadmap()

    def action_run_phases(self) -> None:
        """Run the phases generation."""
        if self.running:
            return
        if not self.files["roadmap"]:
            self.log_message("[red]No roadmap file found. Run Roadmap first.[/red]\n")
            return
        self.run_phase_phases()

    def action_run_prompt(self) -> None:
        """Run the prompt generation."""
        if self.running:
            return
        if not self.files["phase_index"]:
            self.log_message("[red]No phase files found. Run Phases first.[/red]\n")
            return
        self.run_phase_prompt()

    def action_run_install(self) -> None:
        """Install the slash command."""
        if self.running:
            return
        if not self.files["resume_prompt"]:
            self.log_message("[red]No resume prompt found. Run Prompt first.[/red]\n")
            return

        cmd_name = f"resume-{self.slug.replace('_', '-')}"
        commands_dir = self.cwd / ".claude" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)

        cmd_file = commands_dir / f"{cmd_name}.md"
        cmd_file.write_text(self.files["resume_prompt"].read_text())

        self.log_message(f"[green]✓[/green] Installed slash command: [cyan]/{cmd_name}[/cyan]\n")
        self.refresh_status()

    def action_run_execute(self) -> None:
        """Execute work using resume prompt."""
        if self.running:
            return
        if not self.files["resume_prompt"]:
            self.log_message("[red]No resume prompt found. Run Prompt first.[/red]\n")
            return
        self.run_phase_execute()

    @work(exclusive=True)
    async def run_phase_plan(self, description: str) -> None:
        """Run the architecture planning phase."""
        self.running = True
        self.log_message(f"\n[bold cyan]Phase 1: Architecture[/bold cyan]\n")
        self.log_message(f"Planning: {description}\n\n")

        # Ensure docs directory exists
        (self.cwd / "docs").mkdir(exist_ok=True)

        slug = slugify(description)[:30]
        prompt = PROMPTS["architecture"].format(description=description, slug=slug)

        info = await self._run_claude(prompt)
        self.update_info(info.get("total_cost_usd", 0) or 0, info.get("num_turns", 0))

        self.log_message(f"\n[green]✓[/green] Architecture complete: docs/{slug}_ARCHITECTURE.md\n")
        self.refresh_status()
        self.running = False

    @work(exclusive=True)
    async def run_phase_roadmap(self) -> None:
        """Run the roadmap generation phase."""
        self.running = True
        self.log_message(f"\n[bold cyan]Phase 2: Roadmap[/bold cyan]\n")
        self.log_message(f"Reading: {self.files['architecture'].name}\n\n")

        prompt = PROMPTS["roadmap"].format(
            arch_path=self.files["architecture"].relative_to(self.cwd),
            slug=self.slug,
        )

        info = await self._run_claude(prompt)
        self.update_info(info.get("total_cost_usd", 0) or 0, info.get("num_turns", 0))

        self.log_message(f"\n[green]✓[/green] Roadmap complete: docs/{self.slug}_ROADMAP.md\n")
        self.refresh_status()
        self.running = False

    @work(exclusive=True)
    async def run_phase_phases(self) -> None:
        """Run the phase files generation."""
        self.running = True
        self.log_message(f"\n[bold cyan]Phase 3: Phase Files[/bold cyan]\n")
        self.log_message(f"Reading: {self.files['roadmap'].name}\n\n")

        (self.cwd / "docs" / "phases").mkdir(exist_ok=True)

        prompt = PROMPTS["phases"].format(
            roadmap_path=self.files["roadmap"].relative_to(self.cwd),
            slug=self.slug,
        )

        info = await self._run_claude(prompt)
        self.update_info(info.get("total_cost_usd", 0) or 0, info.get("num_turns", 0))

        self.log_message(f"\n[green]✓[/green] Phase files complete: docs/phases/{self.slug}_PHASE_*.md\n")
        self.refresh_status()
        self.running = False

    @work(exclusive=True)
    async def run_phase_prompt(self) -> None:
        """Run the resume prompt generation."""
        self.running = True
        self.log_message(f"\n[bold cyan]Phase 4: Resume Prompt[/bold cyan]\n\n")

        roadmap_path = self.files["roadmap"].relative_to(self.cwd) if self.files["roadmap"] else "docs/ROADMAP.md"

        prompt = PROMPTS["resume_prompt"].format(
            roadmap_path=roadmap_path,
            slug=self.slug,
        )

        info = await self._run_claude(prompt)
        self.update_info(info.get("total_cost_usd", 0) or 0, info.get("num_turns", 0))

        self.log_message(f"\n[green]✓[/green] Resume prompt complete: docs/{self.slug}_RESUME_PROMPT.md\n")
        self.refresh_status()
        self.running = False

    @work(exclusive=True)
    async def run_phase_execute(self) -> None:
        """Execute work using the resume prompt."""
        self.running = True
        self.log_message(f"\n[bold cyan]Executing Work[/bold cyan]\n\n")

        prompt = self.files["resume_prompt"].read_text()

        info = await self._run_claude(prompt)
        self.update_info(info.get("total_cost_usd", 0) or 0, info.get("num_turns", 0))

        self.log_message(f"\n[green]✓[/green] Session complete\n")
        self.refresh_status()
        self.running = False

    async def _run_claude(self, prompt: str) -> dict[str, Any]:
        """Run a Claude Code session and stream output to the log."""
        options = ClaudeCodeOptions(
            cwd=str(self.cwd),
            permission_mode="bypassPermissions",
        )

        result_info: dict[str, Any] = {}
        output = self.query_one("#output", RichLog)

        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        output.write(block.text)
                    elif isinstance(block, ToolUseBlock):
                        output.write(f"[dim]> {block.name}[/dim]")
            elif isinstance(message, ResultMessage):
                result_info = {
                    "duration_ms": message.duration_ms,
                    "num_turns": message.num_turns,
                    "total_cost_usd": message.total_cost_usd,
                    "session_id": message.session_id,
                    "is_error": message.is_error,
                }

        return result_info


def main():
    app = OuterApp()
    app.run()


if __name__ == "__main__":
    main()
