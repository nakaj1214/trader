# feedback-loop — Detailed Procedure

## Trigger Conditions

Activate when the user:
- Gives negative feedback ("違う", "間違い", "そうじゃない")
- Reports repeated issues ("N回目", "また同じ")
- Provides explicit correction instructions

## Step 1: Record in lessons.md

Append entry to `.claude/docs/lessons.md` with classification tags:

```markdown
## [YYYY-MM-DD] {title}
<!-- classification: {category} -->
<!-- severity: {severity} -->

### What happened
...
### Root cause
...
### Rule
...
```

## Step 2: Append to feedback-log.md

Append structured entry to `.claude/docs/feedback-log.md`:

```markdown
## [YYYY-MM-DD] {short description}
- **Classification**: {category}
- **Severity**: {severity}
- **Description**: {what happened}
- **Countermeasure type**: {Rule / Hook / Skill / MCP / Manual}
- **Resolved**: No
- **Related lesson**: [link to lessons.md entry]
```

## Step 3: Update improvement-tracker.md

Read `.claude/docs/improvement-tracker.md`, increment the counter for the matching category, update last occurrence date.

## Step 4: Check Auto-trigger Threshold

If the category count reaches **3 or more**:

1. Determine countermeasure type from the mapping table:

| Category | Countermeasure | Reason |
|----------|---------------|--------|
| 前提違い (wrong assumption) | Rule | Codify as coding convention |
| 手順漏れ (skipped step) | Hook | Auto-check to prevent |
| 規約違反 (rule violation) | Rule | Strengthen existing rule |
| 過剰解釈 (over-interpretation) | Skill | Formalize interpretation procedure |
| 最新情報不足 (outdated info) | MCP | Auto-fetch external info |

2. Append to `.claude/docs/memory/AUTO-MATERIALIZE-QUEUE.jsonl`:

```json
{"ts": "{ISO8601}", "source": "feedback-log.md", "status": "pending", "type": "feedback-pattern", "category": "{category}", "suggested_action": "{Rule/Hook/Skill/MCP}"}
```

3. Notify user:
   「{category} の指摘が3件に達しました。{countermeasure type} の自動生成を提案します。`/materialize` で生成できます」

## Classification Guide

| Category | Criteria | Example |
|----------|----------|---------|
| 前提違い | Factual assumption was wrong | Assumed Bootstrap tabs on custom tab implementation |
| 手順漏れ | Required step was skipped | Forgot AJAX callback verification |
| 規約違反 | Violated documented rule | Changed model name in skill INSTRUCTIONS |
| 過剰解釈 | Over-interpreted user intent | Read "exists" as "has a problem" instead of "remove it" |
| 最新情報不足 | Based decision on outdated info | Suggested non-existent API |

## Severity Guide

| Severity | Criteria |
|----------|----------|
| Must | Completely blocked user's work |
| High | Caused rework |
| Medium | Reduced efficiency but task completed |
| Low | Minor inconvenience |
