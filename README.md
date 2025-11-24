# Outer

Meta-workflow orchestrator for Claude Code planning sessions.

Automates heavy-handed planning for larger tasks (features, refactors, bug fixes) that benefit from structured design before implementation.

## Install

```bash
uv sync
```

## Workflow

Run in any directory where you want to plan work:

```bash
# 1. Design architecture from a description
outer plan "Add user authentication with OAuth support"

# Review docs/add_user_authentication_ARCHITECTURE.md, edit as needed

# 2. Generate implementation roadmap
outer roadmap

# Review docs/add_user_authentication_ROADMAP.md, edit as needed

# 3. Generate detailed phase files with TODOs and acceptance criteria
outer phases

# Review docs/phases/*, edit as needed

# 4. Generate universal resume prompt
outer prompt

# 5. Install as slash command (optional)
outer install

# 6. Execute work
outer run
# or use the slash command: /resume-add-user-authentication
```

## Commands

| Command | Description |
|---------|-------------|
| `outer plan "description"` | Phase 1: Generate architecture document |
| `outer roadmap` | Phase 2: Generate implementation roadmap |
| `outer phases` | Phase 3: Generate detailed phase files |
| `outer prompt` | Phase 4: Generate universal resume prompt |
| `outer install` | Install resume prompt as slash command |
| `outer run` | Execute work using resume prompt |
| `outer status` | Show current workflow status |

## Philosophy

Each phase runs in a fresh Claude Code session to avoid context pollution. Between phases, you review and edit the artifacts. The generated resume prompt is designed to be resilient - you can kill/restart Claude Code at will and use the same prompt to continue.

The workflow produces:
- `docs/{slug}_ARCHITECTURE.md` - Design document
- `docs/{slug}_ROADMAP.md` - Implementation phases
- `docs/phases/{slug}_PHASE_N.md` - Detailed phase files with checkboxes
- `docs/phases/{slug}_PHASE_INDEX.md` - Phase status tracker
- `docs/{slug}_RESUME_PROMPT.md` - Universal resume prompt
- `.claude/commands/resume-{slug}.md` - Slash command (after install)

## Options

```bash
# Custom slug for filenames
outer plan "Add auth" --slug auth_system

# Custom slash command name
outer install --name resume-auth

# Limit turns during execution
outer run --max-turns 50
```
