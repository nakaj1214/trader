# Playbooks — Structured Troubleshooting

## UI Fixes

### "改善されていない（N回目）"

- **Symptom**: User reports no improvement after code change
- **Common Causes**:
  1. jQuery selector doesn't match actual DOM (Bootstrap `a[data-bs-toggle]` vs custom `div.tab[data-tab]`)
  2. AJAX reload callback missing — scroll/state restoration runs before data renders
  3. CSS specificity insufficient — JS-injected styles use `!important` on `box-shadow`, `outline`, `border` (not just `background`)
  4. Japanese requirement over-interpreted — "存在している" simply means "remove it"
- **Fix Steps**:
  1. Re-read prompt.md literally — try simplest 1-line fix first
  2. If fix takes >5 minutes, re-examine your interpretation
  3. Verify event handler selectors match actual DOM elements
  4. Trace AJAX callback chains — ensure post-reload logic runs after render
  5. Check ALL CSS properties injected by JS, not just `background`
- **Verification**: DevTools → Elements → Event Listeners + Computed styles
- **Prevention**: Follow `.claude/rules/ui-fix-verification.md`

### CSS Changes Not Reflected

- **Symptom**: CSS edits don't appear in browser
- **Common Causes**:
  1. JS-injected inline styles with `!important` override stylesheet rules
  2. Specificity too low — class selector loses to ID or inline style
- **Fix Steps**:
  1. DevTools → Computed tab → find which rule actually applies
  2. Use `#id` selector to raise specificity
  3. Override ALL properties from JS injection (list them first)
- **Verification**: DevTools Computed tab shows your rule winning
- **Prevention**: Always inventory JS-injected style properties before writing CSS overrides

---

## Git Issues

### Hook Path Errors After Reorganization

- **Symptom**: Hook scripts fail with `ModuleNotFoundError` or `FileNotFoundError`
- **Common Causes**: `settings.json` hook paths not updated after `hooks/` restructure
- **Fix Steps**:
  1. Update all hook paths in `settings.json`
  2. Check `sys.path.insert` / `_HOOKS_DIR` in each Python script
  3. Verify imports resolve correctly
- **Verification**: `python3 -c "import json; json.load(open('.claude/settings.json'))"`
- **Prevention**: After any hooks/ restructure, grep all path references

---

## Docker Issues

### Commands Fail Inside Container

- **Symptom**: `artisan` or `composer` commands fail
- **Common Causes**: Running commands on host instead of inside container
- **Fix Steps**:
  1. Use `docker compose exec app` prefix for all app commands
  2. Verify container is running: `docker compose ps`
- **Verification**: `docker compose exec app which php`
- **Prevention**: Always prefix with `docker compose exec app`

---

## Test Failures

### Expected Values Don't Match Implementation

- **Symptom**: Tests fail because assertion values don't match actual output
- **Common Causes**: Wrote test expectations without checking implementation output
- **Fix Steps**:
  1. Run function in isolation and inspect actual return value
  2. Update test expectations to match real output
  3. Do NOT weaken assertions — fix the expectation or the code
- **Verification**: `uv run pytest -v <test_file>`
- **Prevention**: Always check actual output before writing assertions

---

## Windows Compatibility

### `import fcntl` Fails

- **Symptom**: `ModuleNotFoundError: No module named 'fcntl'`
- **Common Causes**: `fcntl` is Unix-only
- **Fix Steps**:
  1. Add `sys.platform == "win32"` branch
  2. Use `msvcrt.locking` as fallback
- **Prevention**: Check for platform-specific imports early

### Command Line Length Exceeded

- **Symptom**: Subprocess timeout or truncation on Windows
- **Common Causes**: Windows command line limit ~32KB
- **Fix Steps**: Pass prompts via `stdin` instead of command-line arguments
- **Prevention**: `claude_p.py` uses stdin by default — keep it that way

---

## Skill/Hook Pipeline

### `/materialize` Reports No Pending Entries

- **Symptom**: Queue exists but materialize says nothing to process
- **Common Causes**: All entries already have status `staged`/`approved`/`rejected`
- **Fix Steps**:
  1. `Read .claude/docs/memory/AUTO-MATERIALIZE-QUEUE.jsonl`
  2. Check status field of each entry
  3. If needed, run `/learn-edits` to generate new entries
- **Verification**: `Grep "pending" .claude/docs/memory/AUTO-MATERIALIZE-QUEUE.jsonl`
