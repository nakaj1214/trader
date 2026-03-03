Manage workflow snapshots to track progress at key milestones.

## Usage

```
/checkpoint create <name>   - Save current state as named checkpoint
/checkpoint verify <name>   - Compare current state vs saved checkpoint
/checkpoint list            - Display all saved checkpoints
/checkpoint clear           - Remove old checkpoints (keep last 5)
```

## Create Mode

1. Verify clean working state
2. Create git stash or commit with checkpoint name
3. Log to `.claude/checkpoints.log`:
   ```
   [timestamp] [name] [sha]
   ```

## Verify Mode

Compare against saved checkpoint, reporting changes in:
- Files modified since checkpoint
- Test results (before vs after)
- Code coverage metrics
- Build status

## List Mode

Display all checkpoints:
```
CHECKPOINT          TIMESTAMP           SHA       STATUS
feature-start       2026-02-27 10:00   abc123    behind
auth-complete       2026-02-27 14:00   def456    current
```

## Typical Checkpoint Flow

```
/checkpoint create feature-start
# ... implement auth ...
/checkpoint create auth-complete
/checkpoint verify feature-start    # Shows what changed
# ... implement UI ...
/checkpoint create ui-complete
# Ready for PR
```

Checkpoints integrate with git — each creates a recoverable state you can return to if the implementation direction changes.
