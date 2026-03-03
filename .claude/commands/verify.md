Run comprehensive pre-deploy verification across build, types, linting, tests, and code hygiene.

## Execution Modes

```
/verify           - Full verification (default)
/verify quick     - Build + type checks only
/verify pre-commit - Commit-relevant checks
/verify pre-pr    - Full + security scanning
```

## Verification Steps

Run in sequence — each must pass before proceeding:

### 1. Build Validation
```bash
npm run build     # or cargo build, go build, etc.
```

### 2. Type Checking
```bash
tsc --noEmit      # TypeScript
mypy .            # Python
```

### 3. Linting
```bash
eslint . --max-warnings 0
ruff check .
```

### 4. Test Execution
```bash
npm test -- --coverage
pytest --cov=. --cov-report=term-missing
```

### 5. Console Statement Audit
```bash
grep -r "console\.log\|debugger\|print(" src/ --include="*.ts" --include="*.js"
```

### 6. Git Status Review
```bash
git status
git diff --stat
```

## Report Format

```
## Verification Report

| Check       | Status | Details                    |
|-------------|--------|----------------------------|
| Build       | ✅ PASS |                            |
| Types       | ✅ PASS | 0 errors                   |
| Lint        | ⚠️ WARN | 3 warnings                 |
| Tests       | ✅ PASS | 142/142 | Coverage: 87%    |
| Console     | ❌ FAIL | 2 instances in src/auth.ts |
| Git Status  | ✅ PASS | 5 files changed            |

**Ready for PR:** NO — fix console statements first
```

Any failures provide detailed remediation guidance.
