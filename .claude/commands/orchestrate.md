Run sequential multi-agent workflows where each agent hands off structured context to the next.

## Usage

```
/orchestrate feature     - Full feature implementation
/orchestrate bugfix      - Bug investigation and fix
/orchestrate refactor    - Safe refactoring sequence
/orchestrate security    - Security-focused audit
/orchestrate custom <agents>  - Custom agent sequence (comma-separated)
```

## Built-in Workflows

### Feature Implementation
```
planner → tdd-guide → code-reviewer → security-reviewer
```
Full cycle: plan → test-first → implement → review

### Bug Fix
```
planner → tdd-guide → code-reviewer
```
Investigate → add regression test → fix → review

### Refactor
```
architect → code-reviewer → tdd-guide
```
Design → review current code → ensure test coverage → refactor

### Security Audit
```
security-reviewer → code-reviewer
```
Security scan → full quality review

## Handoff Document (Between Agents)

Each agent produces a structured handoff:

```markdown
## Handoff: [Agent Name] → [Next Agent]

### Summary
What was accomplished in this phase.

### Key Findings
- [Important discovery 1]
- [Important discovery 2]

### Files Modified
- [path/to/file.ts] — [what changed]

### Unresolved Items
- [What needs attention next]

### Recommended Next Steps
[Specific instructions for next agent]
```

## Final Report

```markdown
## Orchestration Complete

### Agents Run
1. [agent] — [summary]
2. [agent] — [summary]

### Files Modified
- [file list]

### Test Results
[Pass/fail counts]

### Recommendation
**SHIP** / **NEEDS WORK** / **BLOCKED**
[Reasoning]
```

## Custom Workflows

```
/orchestrate custom architect,code-reviewer,tdd-guide,security-reviewer
```

Agents run in the specified order with structured handoffs between each.
