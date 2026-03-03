Review uncommitted code changes across three severity tiers. Delegates to the code-reviewer agent.

## Process

### 1. Identify Changes
```bash
git diff HEAD
git diff --staged
git status
```

### 2. Three-Tier Review

**CRITICAL (Block)**
- Hardcoded credentials, API keys, tokens
- SQL injection vulnerabilities
- XSS attack vectors
- Authentication bypasses
- Path traversal risks
- "Never approve code with security vulnerabilities!"

**HIGH (Fix Before Merge)**
- Functions exceeding 50 lines
- Files over 800 lines
- Nesting depth beyond 4 levels
- Missing error handling
- Debug statements left in code (`console.log`, `print`, `debugger`)
- Insufficient test coverage for new logic

**MEDIUM (Recommended)**
- Mutable shared state patterns
- Missing accessibility attributes
- Test coverage gaps
- Inconsistent naming conventions

### 3. Output Format

```markdown
## Code Review: [scope]

### CRITICAL Issues
- [file:line] Issue + remediation

### HIGH Issues
- [file:line] Issue + remediation

### MEDIUM Issues
- [file:line] Suggestion

### Verdict: [Approve / Warning / Block]
```

**Rule:** Block commits on critical or high-priority issues. Provide remediation with every finding.
