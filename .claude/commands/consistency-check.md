Run cross-module consistency checks and fix issues found. Use after multi-session development or when features are added in parallel.

## Execution Modes

```
/consistency-check           - Full check (all layers)
/consistency-check quick     - Imports + config only
/consistency-check fix       - Check and auto-fix all issues
/consistency-check <layer>   - Check specific layer (imports, config, types, routes, tests)
```

## Check Layers

Run checks in dependency order — earlier layers must pass before later ones are meaningful:

### 1. Import Consistency
Verify all imports resolve to existing modules/exports.

**Python (`src/`):**
- Every `from src.X import Y` must reference an existing module and exported symbol
- Check `__init__.py` re-exports match actual definitions
- Verify no circular imports between core modules

**TypeScript (`dashboard-v2/src/`):**
- Every `$lib/` import must reference an existing file and exported symbol
- Every relative import in Svelte components must resolve
- Chart.js imports must use `chart.js/auto`

**Action:** Use Explore agent to trace all import statements across all source files.

### 2. Config Consistency
Verify config files match code expectations.

- `config/default.yaml` sections must match `src/core/config.py` Pydantic classes
- All validator-allowed values (e.g., `_VALID_ANALYSIS_TYPES`, `_VALID_MODELS`) must include every type used in code
- `pyproject.toml` dependencies must cover all `import` statements
- `pyproject.toml` `build-backend` must be a valid public API
- `package.json` dependencies must cover all `import` statements in TS/Svelte

**Action:** Cross-reference YAML keys against Pydantic field names; cross-reference registered types against actual class `name` properties.

### 3. Type / Model Consistency
Verify data models match usage across modules.

- Every field accessed on a model must be defined in that model class
- Type annotations must match actual values passed
- Pydantic validators must not reject valid config values
- TypeScript interfaces must match JSON data schemas

**Action:** Trace field access patterns across modules and compare against model definitions.

### 4. Route / Page Consistency
Verify all routes are properly registered and linked.

- `svelte.config.js` `prerender.entries` must list all route directories
- Every `<a href>` in components must point to a valid route
- Navigation components (Header, landing page) must link to all pages
- New pages in `dashboard/` must have corresponding routes in `dashboard-v2/`

**Action:** Glob all route directories, compare against prerender entries and nav links.

### 5. Test Consistency
Verify tests match current code.

- Test imports must reference existing modules and symbols
- `conftest.py` fixtures must not conflict across test files
- Test assertions must reference existing fields/methods
- No tests left for deleted or renamed modules

**Action:** Cross-reference test imports against source modules.

### 6. Registration Consistency
Verify all pluggable components are registered.

- Analysis: every `*_analyzer.py` must be in `runner.py._get_all_analyzers()` AND `_VALID_ANALYSIS_TYPES`
- CLI: every registered type must be accepted by CLI argument parsing
- Templates: every analyzer name must have a matching template constant

**Action:** Enumerate all analyzer files, cross-reference against registration points.

## Fix Strategy

When `fix` mode is used, apply fixes in this order:

1. **Safe fixes (auto-apply):**
   - Merge duplicate imports from same module
   - Add missing entries to `prerender.entries`
   - Add missing analyzer types to `_VALID_ANALYSIS_TYPES`
   - Fix `build-backend` to public API

2. **Cautious fixes (apply with explanation):**
   - Add missing dependencies to `pyproject.toml` / `package.json`
   - Add missing route files for new pages
   - Update CLI help strings

3. **Manual fixes (report only):**
   - Circular import restructuring
   - Model field mismatches
   - Config validator logic changes

## Report Format

```markdown
## Consistency Check Report

| Layer          | Status  | Issues | Auto-fixable |
|----------------|---------|--------|--------------|
| Imports        | ✅ PASS  | 0      | -            |
| Config         | ⚠️ WARN  | 2      | 1            |
| Types/Models   | ✅ PASS  | 0      | -            |
| Routes/Pages   | ❌ FAIL  | 1      | 1            |
| Tests          | ✅ PASS  | 0      | -            |
| Registration   | ✅ PASS  | 0      | -            |

### Issues Found

#### [LAYER] Issue Title
- **File:** `path/to/file.py:42`
- **Problem:** Description
- **Fix:** Applied / Needs manual fix
- **Severity:** High / Medium / Low
```

## Subagent Strategy

Use parallel Explore agents for independent checks:
- Agent 1: Python imports + registration (src/)
- Agent 2: TypeScript imports + routes (dashboard-v2/src/)
- Agent 3: Config + types cross-reference

Merge results into unified report.

## Guidelines

- Never modify code without reading it first
- Apply smallest possible fix for each issue
- Run tests after auto-fixes when possible
- Report issues you cannot safely auto-fix
- Check both `dashboard/` (legacy) and `dashboard-v2/` (new) when relevant
- Track all changes in the report for user review
