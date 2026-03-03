# Security Rules

## Pre-Commit Security Checklist

Before every commit, verify:

- [ ] No hardcoded secrets (API keys, passwords, tokens)
- [ ] All user inputs validated at system boundaries
- [ ] SQL queries use parameterized statements
- [ ] XSS protection in place for all user-generated content
- [ ] CSRF protection on state-changing endpoints
- [ ] Authentication properly implemented on protected routes

## Secret Handling

**NEVER commit secrets to version control.**

```bash
# ❌ Bad
const API_KEY = "sk-abc123..."

# ✅ Good
const API_KEY = process.env.API_KEY
```

- Use environment variables or a secret manager
- Verify required secrets exist at application startup
- Rotate credentials immediately if exposed

## Incident Response

When a security vulnerability is discovered:

1. **Stop** — cease current work immediately
2. **Escalate** — delegate to the **security-reviewer** agent
3. **Fix** — remediate critical flaws before resuming
4. **Rotate** — change credentials if exposure occurred
5. **Audit** — review codebase for similar vulnerabilities

## Input Validation

Validate at **all system boundaries**:
- User form inputs
- URL parameters and query strings
- External API response data
- File uploads (type, size, content)
- Webhook payloads
