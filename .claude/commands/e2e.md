Generate and execute end-to-end tests for critical user journeys. Delegates to the e2e-runner agent.

## When to Use

Use for testing multi-step user flows:
- Authentication (login, logout, registration)
- Core business workflows (checkout, payment, trading)
- User data CRUD operations
- Cross-service integrations

⚠️ **Financial flows must run on testnet/staging only — never production.**

## What Runs

1. **Journey Analysis** — Identify critical user paths in the codebase
2. **Test Generation** — Create Playwright tests using Page Object Model
3. **Multi-Browser Execution** — Chromium, Firefox, WebKit
4. **Artifact Capture** — Screenshots, videos, traces on failure
5. **Flaky Detection** — Identify and quarantine unstable tests

## Artifact Output

All runs produce:
- HTML test report
- JUnit XML results

Failures additionally generate:
- Screenshots at failure point
- Video recording of test session
- Playwright trace (step-by-step replay)
- Network and console logs

## Quality Targets

| Metric | Target |
|--------|--------|
| Critical journeys | 100% pass |
| Overall pass rate | >95% |
| Flaky test rate | <5% |
| Suite runtime | <10 min |

## Flaky Test Handling

Intermittent failures trigger recommendations to:
- Add explicit wait conditions
- Increase element visibility timeouts
- Check for race conditions in async operations
- Add retry logic for network-dependent steps
