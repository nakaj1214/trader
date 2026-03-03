Safely remove dead code, unused exports, and redundant implementations. Delegates to the refactor-cleaner agent.

## Detection Tools

```bash
npx knip              # Unused files and exports (JS/TS)
npx depcheck          # Unused npm dependencies
npx ts-prune          # TypeScript unused exports
npx eslint --report-unused-disable-directives .  # Unused directives

# Language-specific
vulture .             # Python dead code
deadcode ./...        # Go dead code
cargo-udeps           # Rust unused dependencies
```

## Risk Classification

| Risk | Examples | Action |
|------|---------|--------|
| **SAFE** | Unused utilities, unreachable code | Delete confidently |
| **CAUTION** | Components, routes | Verify no dynamic usage |
| **DANGER** | Config files, entry points | Investigate thoroughly |

## Process

1. **Run tests first** — establish baseline
2. **Delete one item** — smallest possible change
3. **Re-run tests** — confirm nothing broke
4. **Revert immediately** if anything fails
5. **Repeat** for next item

## Before Removing CAUTION Items

Check for dynamic usage:
```bash
grep -r "dynamicImport\|require(" src/
grep -r "symbolName" --include="*.ts" .
```

## Consolidation

After cleanup, identify near-duplicate functions:
- Merge into single shared implementation
- Update all callers to use unified version
- Remove originals

## Final Report

```
### Cleanup Summary
- Removed: [N lines, M files]
- Unused deps removed: [packages]
- Consolidated: [N duplicate functions merged]
- Skipped: [items too uncertain to remove]
- Tests: [X passing] — no regressions
```

**Rule:** Never delete without running tests first. One change at a time.
