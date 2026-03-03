# Git Workflow Rules

## Commit Message Format

```
<type>: <description>

[optional body]
```

### Allowed Types

| Type | When to Use |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `refactor` | Code change with no behavior change |
| `docs` | Documentation only |
| `test` | Adding or updating tests |
| `chore` | Tooling, deps, build scripts |
| `perf` | Performance improvement |
| `ci` | CI/CD configuration |

### Examples

```
feat: add user authentication with JWT
fix: resolve race condition in cache invalidation
refactor: extract payment logic into service class
docs: update API endpoint documentation
test: add integration tests for auth flow
```

## Pull Request Process

1. Review the **complete commit history** (not just individual commits)
2. Run `git diff [base-branch]...HEAD` to see all changes
3. Write a detailed PR description covering:
   - What changed and why
   - Testing strategy with checklist
   - Breaking changes (if any)
4. Use `-u` flag when pushing new branches: `git push -u origin branch-name`

## Branch Naming

```
feat/short-description
fix/issue-number-description
refactor/module-name
```
