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

import click
from rich.console import Console
from rich.panel import Panel

from claude_code_sdk import (
    query,
    ClaudeCodeOptions,
    TextBlock,
    ToolUseBlock,
    ResultMessage,
    AssistantMessage,
)

console = Console()


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

    # Find architecture file
    for f in docs.glob("*_ARCHITECTURE.md"):
        result["architecture"] = f
        break

    # Find roadmap file
    for f in docs.glob("*_ROADMAP.md"):
        result["roadmap"] = f
        break

    # Find phase index
    if phases_dir.exists():
        for f in phases_dir.glob("*_PHASE_INDEX.md"):
            result["phase_index"] = f
            break

    # Find resume prompt
    for f in docs.glob("*_RESUME_PROMPT.md"):
        result["resume_prompt"] = f
        break

    return result


def get_slug_from_files(files: dict[str, Path | None]) -> str | None:
    """Extract the project slug from existing files."""
    for key in ["architecture", "roadmap", "resume_prompt"]:
        if files[key]:
            name = files[key].stem
            # Remove the suffix to get the slug
            for suffix in ["_ARCHITECTURE", "_ROADMAP", "_RESUME_PROMPT"]:
                if name.endswith(suffix):
                    return name[:-len(suffix)]
    if files["phase_index"]:
        name = files["phase_index"].stem
        if name.endswith("_PHASE_INDEX"):
            return name[:-len("_PHASE_INDEX")]
    return None


async def run_claude(
    prompt: str,
    cwd: Path,
    max_turns: int | None = None,
) -> dict[str, Any]:
    """Run a Claude Code session and stream output."""
    options = ClaudeCodeOptions(
        cwd=str(cwd),
        max_turns=max_turns,
        permission_mode="bypassPermissions",
    )

    result_info: dict[str, Any] = {}

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    console.print(block.text, end="")
                elif isinstance(block, ToolUseBlock):
                    console.print(f"\n[dim]> {block.name}[/dim]")
        elif isinstance(message, ResultMessage):
            result_info = {
                "duration_ms": message.duration_ms,
                "num_turns": message.num_turns,
                "total_cost_usd": message.total_cost_usd,
                "session_id": message.session_id,
                "is_error": message.is_error,
            }

    console.print()
    return result_info


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


@click.group()
def cli():
    """Outer - Meta-workflow orchestrator for Claude Code planning sessions."""
    pass


@cli.command()
@click.argument("description")
@click.option("--slug", "-s", help="Custom slug for filenames (default: derived from description)")
def plan(description: str, slug: str | None) -> None:
    """Phase 1: Generate architecture document from a description."""
    cwd = Path.cwd()

    # Create docs directory
    docs = cwd / "docs"
    docs.mkdir(exist_ok=True)

    project_slug = slug or slugify(description)[:30]

    prompt = PROMPTS["architecture"].format(
        description=description,
        slug=project_slug,
    )

    console.print(Panel(
        f"[yellow]Planning:[/yellow] {description}\n"
        f"[dim]Slug: {project_slug}[/dim]",
        title="Phase 1: Architecture",
    ))
    console.print()

    async def run():
        info = await run_claude(prompt, cwd)
        console.print(Panel(
            f"[green]Architecture complete[/green]\n\n"
            f"Output: docs/{project_slug}_ARCHITECTURE.md\n"
            f"Cost: ${info.get('total_cost_usd', 0):.4f}\n\n"
            "[dim]Review and edit, then run:[/dim] outer roadmap",
            title="Done",
        ))

    asyncio.run(run())


@cli.command()
def roadmap() -> None:
    """Phase 2: Generate implementation roadmap from architecture."""
    cwd = Path.cwd()
    files = find_planning_files(cwd)

    if not files["architecture"]:
        console.print("[red]No architecture file found in docs/[/red]")
        console.print("Run 'outer plan \"description\"' first.")
        raise SystemExit(1)

    slug = get_slug_from_files(files)

    prompt = PROMPTS["roadmap"].format(
        arch_path=files["architecture"].relative_to(cwd),
        slug=slug,
    )

    console.print(Panel(
        f"[yellow]Reading:[/yellow] {files['architecture'].name}",
        title="Phase 2: Roadmap",
    ))
    console.print()

    async def run():
        info = await run_claude(prompt, cwd)
        console.print(Panel(
            f"[green]Roadmap complete[/green]\n\n"
            f"Output: docs/{slug}_ROADMAP.md\n"
            f"Cost: ${info.get('total_cost_usd', 0):.4f}\n\n"
            "[dim]Review and edit, then run:[/dim] outer phases",
            title="Done",
        ))

    asyncio.run(run())


@cli.command()
def phases() -> None:
    """Phase 3: Generate detailed phase planning files."""
    cwd = Path.cwd()
    files = find_planning_files(cwd)

    if not files["roadmap"]:
        console.print("[red]No roadmap file found in docs/[/red]")
        console.print("Run 'outer roadmap' first.")
        raise SystemExit(1)

    # Create phases directory
    (cwd / "docs" / "phases").mkdir(exist_ok=True)

    slug = get_slug_from_files(files)

    prompt = PROMPTS["phases"].format(
        roadmap_path=files["roadmap"].relative_to(cwd),
        slug=slug,
    )

    console.print(Panel(
        f"[yellow]Reading:[/yellow] {files['roadmap'].name}",
        title="Phase 3: Phase Files",
    ))
    console.print()

    async def run():
        info = await run_claude(prompt, cwd)
        console.print(Panel(
            f"[green]Phase files complete[/green]\n\n"
            f"Output: docs/phases/{slug}_PHASE_*.md\n"
            f"Cost: ${info.get('total_cost_usd', 0):.4f}\n\n"
            "[dim]Review and edit, then run:[/dim] outer prompt",
            title="Done",
        ))

    asyncio.run(run())


@cli.command()
def prompt() -> None:
    """Phase 4: Generate universal resume prompt."""
    cwd = Path.cwd()
    files = find_planning_files(cwd)

    if not files["phase_index"]:
        console.print("[red]No phase index found in docs/phases/[/red]")
        console.print("Run 'outer phases' first.")
        raise SystemExit(1)

    slug = get_slug_from_files(files)

    prompt_text = PROMPTS["resume_prompt"].format(
        roadmap_path=files["roadmap"].relative_to(cwd) if files["roadmap"] else "docs/ROADMAP.md",
        slug=slug,
    )

    console.print(Panel(
        f"[yellow]Generating resume prompt for:[/yellow] {slug}",
        title="Phase 4: Resume Prompt",
    ))
    console.print()

    async def run():
        info = await run_claude(prompt_text, cwd)
        console.print(Panel(
            f"[green]Resume prompt complete[/green]\n\n"
            f"Output: docs/{slug}_RESUME_PROMPT.md\n"
            f"Cost: ${info.get('total_cost_usd', 0):.4f}\n\n"
            "[dim]Install as slash command:[/dim] outer install\n"
            "[dim]Or run directly:[/dim] outer run",
            title="Done",
        ))

    asyncio.run(run())


@cli.command()
@click.option("--name", "-n", help="Custom command name (default: resume-{slug})")
def install(name: str | None) -> None:
    """Install resume prompt as a Claude Code slash command."""
    cwd = Path.cwd()
    files = find_planning_files(cwd)

    if not files["resume_prompt"]:
        console.print("[red]No resume prompt found in docs/[/red]")
        console.print("Run 'outer prompt' first.")
        raise SystemExit(1)

    slug = get_slug_from_files(files)
    cmd_name = name or f"resume-{slug.replace('_', '-')}"

    # Create command directory and file
    commands_dir = cwd / ".claude" / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)

    cmd_file = commands_dir / f"{cmd_name}.md"
    cmd_file.write_text(files["resume_prompt"].read_text())

    console.print(Panel(
        f"[green]Slash command installed![/green]\n\n"
        f"Command: [cyan]/{cmd_name}[/cyan]\n"
        f"File: .claude/commands/{cmd_name}.md\n\n"
        "Usage:\n"
        "  1. Start fresh Claude Code session\n"
        f"  2. Type [cyan]/{cmd_name}[/cyan]\n"
        "  3. Work resumes automatically\n\n"
        "Kill/restart freely - use the command each time.",
        title="Installed",
    ))


@cli.command()
@click.option("--max-turns", "-t", type=int, help="Maximum turns for the session")
def run(max_turns: int | None) -> None:
    """Execute work using the resume prompt."""
    cwd = Path.cwd()
    files = find_planning_files(cwd)

    if not files["resume_prompt"]:
        console.print("[red]No resume prompt found in docs/[/red]")
        console.print("Run 'outer prompt' first.")
        raise SystemExit(1)

    prompt_text = files["resume_prompt"].read_text()

    console.print(Panel(
        "[yellow]Starting work session...[/yellow]",
        title="Run",
    ))
    console.print()

    async def execute():
        info = await run_claude(prompt_text, cwd, max_turns=max_turns)
        console.print(Panel(
            f"[green]Session complete[/green]\n\n"
            f"Cost: ${info.get('total_cost_usd', 0):.4f}\n"
            f"Turns: {info.get('num_turns', 0)}\n\n"
            "Progress saved to phase files.\n"
            "[dim]Continue with:[/dim] outer run",
            title="Done",
        ))

    asyncio.run(execute())


@cli.command()
def status() -> None:
    """Show current planning workflow status."""
    cwd = Path.cwd()
    files = find_planning_files(cwd)
    slug = get_slug_from_files(files)

    phases = [
        ("Architecture", files["architecture"]),
        ("Roadmap", files["roadmap"]),
        ("Phase Files", files["phase_index"]),
        ("Resume Prompt", files["resume_prompt"]),
    ]

    lines = []
    for name, path in phases:
        if path:
            lines.append(f"  [green]✓[/green] {name}: {path.relative_to(cwd)}")
        else:
            lines.append(f"  [dim]•[/dim] {name}")

    # Check for slash command
    if slug:
        cmd_file = cwd / ".claude" / "commands" / f"resume-{slug.replace('_', '-')}.md"
        if cmd_file.exists():
            lines.append(f"  [green]✓[/green] Slash command: /{cmd_file.stem}")
        else:
            lines.append(f"  [dim]•[/dim] Slash command")

    title = slug or "No project found"
    console.print(Panel("\n".join(lines), title=title))


def main():
    cli()


if __name__ == "__main__":
    main()
