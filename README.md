# Outer

Meta-workflow orchestrator for Claude Code planning sessions.

A TUI that automates heavy-handed planning for larger tasks (features, refactors, bug fixes) that benefit from structured design before implementation.

## Install

```bash
uv sync
```

## Usage

```bash
uv run outer
```

This launches a TUI with:
- **Sidebar**: Shows workflow status and action buttons
- **Main panel**: Streams Claude Code output
- **Footer**: Shows keybindings

## Workflow

1. Press `1` or click "Plan" - Enter a project description
2. Review `docs/{slug}_ARCHITECTURE.md`, edit as needed
3. Press `2` or click "Roadmap" - Generates implementation phases
4. Review `docs/{slug}_ROADMAP.md`, edit as needed
5. Press `3` or click "Phases" - Generates detailed phase files
6. Review `docs/phases/*`, edit as needed
7. Press `4` or click "Prompt" - Generates resume prompt
8. Press `5` or click "Install" - Installs as slash command
9. Press `6` or click "Run" - Executes work

## Keybindings

| Key | Action |
|-----|--------|
| `1` | Start planning (enter description) |
| `2` | Generate roadmap |
| `3` | Generate phase files |
| `4` | Generate resume prompt |
| `5` | Install slash command |
| `6` | Run/execute work |
| `r` | Refresh status |
| `c` | Clear output |
| `q` | Quit |

## Philosophy

Each phase runs in a fresh Claude Code session to avoid context pollution. Between phases, you review and edit the artifacts. The generated resume prompt is designed to be resilient - you can kill/restart Claude Code at will and use the same prompt to continue.

## Output Files

- `docs/{slug}_ARCHITECTURE.md` - Design document
- `docs/{slug}_ROADMAP.md` - Implementation phases
- `docs/phases/{slug}_PHASE_N.md` - Detailed phase files with checkboxes
- `docs/phases/{slug}_PHASE_INDEX.md` - Phase status tracker
- `docs/{slug}_RESUME_PROMPT.md` - Universal resume prompt
- `.claude/commands/resume-{slug}.md` - Slash command (after install)
