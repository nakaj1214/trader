Synchronize project documentation with current codebase state, generating from source rather than manual editing.

## Sources of Truth

Extract documentation content from actual code:

| Source File | Documents |
|------------|-----------|
| `package.json` scripts | Available commands table |
| `.env.example` | Environment variables reference |
| API route files | Endpoint documentation |
| `Dockerfile` / `docker-compose.yml` | Deployment procedures |
| Migration files | Database schema changes |

## Critical Rules

- **Generate from code, never manually edit generated sections**
- **Only update generated sections — leave hand-written prose intact**
- **Mark auto-generated content** with `<!-- AUTO-GENERATED -->` comments
- **Don't create documentation files** without explicit request

## Process

### 1. Scan for Changes
```bash
git diff HEAD~1 --name-only   # Files changed since last commit
git log --oneline -10          # Recent changes context
```

### 2. Extract and Update

**Scripts table** (from package.json):
```markdown
| Command | Description |
|---------|-------------|
| npm run dev | Start development server |
| npm run build | Production build |
| npm test | Run test suite |
```

**Environment variables** (from .env.example):
```markdown
| Variable | Required | Example | Description |
|----------|----------|---------|-------------|
| DATABASE_URL | ✅ | postgresql://... | Database connection |
| JWT_SECRET | ✅ | change-me | Auth token signing |
```

### 3. Staleness Check

Flag documentation older than 90 days that may be outdated:
```bash
git log --oneline -- README.md | head -1  # Last README update
```

## Output Report

```
## Documentation Updated

### Updated
- README.md — scripts table, env vars section
- docs/api.md — 3 new endpoints added

### Skipped (no changes detected)
- CONTRIBUTING.md
- docs/architecture.md

### Stale (>90 days, needs review)
- docs/deployment.md — last updated 2025-10-15
```
