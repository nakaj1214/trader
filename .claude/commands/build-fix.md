Systematically resolve build and type errors with minimal, incremental changes.

## Workflow

### 1. Detect Build System
Identify the project type from manifest files:
- `package.json` → `npm run build` / `tsc --noEmit`
- `Cargo.toml` → `cargo build`
- `pom.xml` → `mvn compile`
- `go.mod` → `go build ./...`
- `pyproject.toml` → `python -m py_compile`

### 2. Capture and Organize Errors
```bash
# Run build and capture all errors
npm run build 2>&1 | tee build-errors.txt
```

Group errors by:
1. Import/dependency issues (fix first)
2. Type errors
3. Logic-level errors

### 3. Iterative Resolution Loop
For each error:
1. Read the affected code section
2. Identify root cause
3. Apply smallest possible fix
4. Rebuild to confirm improvement

### 4. Escalation Checkpoints
Stop and consult user when:
- Fix generates additional errors
- Same error persists after 3 attempts
- Changes require structural redesign
- Missing packages can't be installed

### 5. Recovery Techniques

| Problem | Solution |
|---------|---------|
| Missing package | `npm install <pkg>` or `pip install <pkg>` |
| Type incompatibility | Add type assertion or fix actual type |
| Circular import | Extract shared code to new module |
| Version conflict | Pin versions or update lockfile |
| Config error | Check tsconfig/webpack/vite config |

**Principle:** One error at a time. Never refactor unrelated code.
