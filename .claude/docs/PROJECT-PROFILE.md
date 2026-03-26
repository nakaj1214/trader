# Project Profile

## Identity

- **Repository**: nakaj_claude
- **Purpose**: Claude Code configuration and automation toolkit — skills, hooks, rules, agents を集約したメタプロジェクト
- **Owner**: nakashima

## Tech Stack

| Category | Technologies |
|----------|-------------|
| Primary | Python 3.12+ (hooks, scripts, meta tools) |
| Frontend | jQuery + Laravel Blade (target projects) |
| Backend | Laravel 10/11/12, PHP 8.x (target projects) |
| Hardware | ESP32 (PlatformIO + Arduino), Raspberry Pi (Python) |
| Package Mgmt | uv (Python), npm (JS), Composer (PHP) |
| Linting | ruff (Python), ESLint (JS) |
| Type Check | ty (Python) |
| Testing | pytest (Python), Pest (PHP) |

## Directory Structure

```
.claude/
├── agents/          # 22 specialist sub-agents
├── commands/        # 26 slash commands (/commit, /review-pr, etc.)
├── docs/            # Knowledge base + memory
│   ├── memory/      # HANDOVER, EDIT-PATTERNS, SKILL-SUGGESTIONS
│   ├── references/  # Security, agents, git, plugin-dev references
│   ├── lessons.md   # Captured mistakes & rules
│   └── playbooks.md # Structured troubleshooting
├── hooks/           # Event-driven automation (6 active hooks)
│   └── lib/         # Shared utilities (transcript, claude_p)
├── meta/            # Self-maintenance (generate-registry.py, health-check.py)
├── registry/        # skills.yaml (auto-generated index)
├── rules/           # 26 coding rules (9 always-loaded + 17 conditional)
├── skills/          # 42 workflow recipes
└── staging/         # Pipeline staging area + STAGING-MANIFEST.json
```

## Startup / Test / CI Procedures

```bash
# Python
uv run ruff check .              # Lint
uv run ruff format .             # Format
uv run ty check src/             # Type check
uv run pytest -v                 # Test

# Meta tools
python3 .claude/meta/generate-registry.py   # Rebuild skills.yaml
python3 .claude/meta/health-check.py        # Skill quality audit

# PHP/Laravel (Docker)
docker compose exec app php artisan test
docker compose exec app ./vendor/bin/pest
```

## Frequently Touched Modules

| File | Role |
|------|------|
| `.claude/settings.json` | Hook registration, permissions |
| `.claude/CLAUDE.md` | Session behavior, workflow rules |
| `.claude/docs/memory/` | HANDOVER, EDIT-PATTERNS, QUEUE |
| `.claude/hooks/quality/edit-tracker.py` | Edit logging |
| `.claude/hooks/session/pre-compact-handover.py` | Context preservation |
| `.claude/registry/skills.yaml` | Skill routing index |

## Known Gotchas

- **Windows**: `fcntl` unavailable — use `msvcrt` fallback
- **Windows**: Command line length limit ~32KB — use stdin for large payloads
- **Windows**: `claude -p` nesting — must unset `CLAUDECODE` env var
- **UI**: Bootstrap tab selectors don't work on custom tab implementations (`<div class="tab" data-tab>`)
- **Hooks**: `delay()` in edit hooks risks timeout (SYNTAX_CHECK_TIMEOUT = 3s)
- **DataTables**: Use `scroller.toPosition(rowIndex)` not `scrollTop(px)`

## Reference Docs

- `.claude/STRUCTURE.md` — Complete directory map
- `.claude/context-management.md` — Context budget management (200K total, 80K danger)
- `.claude/docs/DESIGN.md` — Architectural decisions
