Analyze test coverage and generate missing tests to reach 80%+ coverage threshold.

## Step 1: Detect Framework and Run Coverage

```bash
# Detect framework
ls jest.config.* vitest.config.* pytest.ini 2>/dev/null

# Run coverage
npx jest --coverage                          # Jest
npx vitest run --coverage                    # Vitest
pytest --cov=. --cov-report=term-missing     # pytest
go test -coverprofile=coverage.out ./...     # Go
```

## Step 2: Identify Gaps

From coverage report, find:
- Under-covered files (<80%)
- Untested functions or methods
- Missing branch coverage (if/else, switch, error paths)
- Dead code inflating the denominator

## Step 3: Test Generation Priority

For each gap, write tests in this order:
1. **Happy path** — valid input, expected output
2. **Failure scenarios** — invalid input, error returns
3. **Boundary conditions** — empty, null, zero, MAX values
4. **Branch coverage** — all conditional paths

## Test Quality Standards

- Each test is independent (no shared mutable state)
- Descriptive naming: `test_create_user_with_duplicate_email_returns_409`
- Follow existing project test conventions for file location and imports
- Mock external services — tests must not make real network calls

## Priority Targets

Focus on:
1. High-complexity functions (cyclomatic complexity > 5)
2. Error handling paths
3. Utility and helper functions
4. API endpoints and controllers
5. Edge cases: null, empty collections, numeric boundaries

## Report Format

```markdown
## Coverage Improvement

| File | Before | After | Delta |
|------|--------|-------|-------|
| auth/login.ts | 45% | 87% | +42% |
| utils/format.ts | 12% | 91% | +79% |

**Overall:** 67% → 84% (+17%)
Tests added: 23 | All passing ✅
```
