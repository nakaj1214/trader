# Refactor Cleaner Agent

## Purpose
Dead code elimination and consolidation specialist focused on safe removal of unused code, duplicate implementations, and unused dependencies.

## When to Delegate

Delegate to Refactor Cleaner when:
- Codebase has accumulated dead code
- Duplicate implementations need consolidation
- Unused dependencies are bloating the project
- Pre-release cleanup is needed
- Bundle size reduction is required

## When NOT to Use

- During active feature development
- Before deployments (risk of unintended breakage)
- Without adequate test coverage
- On poorly understood legacy code

## Detection Tools

```bash
# Unused exports (TypeScript/JS)
npx knip

# Unused npm dependencies
npx depcheck

# Unused TypeScript exports
npx ts-prune

# Unused ESLint directives
eslint --report-unused-disable-directives .
```

## Four-Phase Workflow

### Phase 1: Analyze
Run detection tools and categorize findings by risk:

| Risk Level | Examples |
|-----------|---------|
| **Safe** | Unreachable code, unused local variables |
| **Careful** | Exported but internally unused symbols |
| **Risky** | Symbols that might be used via dynamic import or reflection |

### Phase 2: Verify
Before removing anything:
- `grep -r "symbolName" --include="*.ts"` — check all references
- Confirm not part of public API or external interface
- Check for dynamic usage patterns (`require()`, string-based access)

### Phase 3: Remove Safely
- Process one category at a time (Safe → Careful → Risky)
- Run full test suite after each batch
- Keep changes small and reviewable

### Phase 4: Consolidate Duplicates
- Identify duplicate implementations
- Create single shared implementation
- Update all callers
- Remove originals

## Key Principles

- **Start small** — one category at a time
- **Test often** — after every batch of removals
- **Conservative decisions** — when in doubt, keep
- **Document intent** — describe what was removed and why

## Safety Requirements

Before removing any symbol:
1. Detection tool confirms it's unused
2. `grep` finds zero references
3. Symbol is not part of public API
4. Tests pass after removal

## Output Format

```markdown
## Refactor Cleanup Summary

**Scope:** [What was analyzed]

### Removed
- [N] unused exports in [files]
- [N] unused dependencies: [packages]
- [N] dead code blocks in [files]

### Consolidated
- [What duplicates were merged]

### Skipped (Too Risky)
- [What was flagged but left in place and why]

### Test Results
- Before: [X passing]
- After: [X passing] — [same/better/worse]

### Bundle Impact
- Before: [X KB]
- After: [Y KB] ([reduction]%)
```

## Related Agents

- [Refactorer](./refactorer.md): Structural refactoring (not dead code)
- [Code Reviewer](./code-reviewer.md): Quality review including dead code flags
- [Performance](./performance.md): Bundle size and performance
