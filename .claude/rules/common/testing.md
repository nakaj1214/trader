# Testing Requirements

## Coverage Standard

**Minimum 80% test coverage** across all modules.

## Required Test Types

| Type | Scope | Example |
|------|-------|---------|
| **Unit** | Isolated functions/classes | `test_calculate_total_with_discount` |
| **Integration** | System interactions | `test_user_creation_persists_to_db` |
| **E2E** | Full user workflows | `test_checkout_flow_completes_order` |

## Test-Driven Development Cycle

```
RED    → Write failing test first
VERIFY → Confirm test actually fails
GREEN  → Implement minimal code to pass
VERIFY → Confirm test passes
REFACTOR → Clean up, maintain green
MEASURE → Confirm 80%+ coverage
```

**Write tests first, always. No exceptions.**

## TDD Agent

When implementing new features, use the **tdd-guide** agent to:
- Ensure tests are written before implementation
- Maintain the Red-Green-Refactor cycle
- Validate coverage metrics after completion

## Test Independence

- Each test runs independently (no shared mutable state)
- Tests can run in any order
- Tests clean up after themselves
- External services are mocked in unit tests

## When Tests Fail

1. Never weaken test assertions to make tests pass
2. Fix the actual code, not the tests
3. Use the **tdd-guide** agent if stuck
