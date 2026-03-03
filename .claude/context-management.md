# Context Management Guide

Managing Claude's context window effectively is critical for performance and cost optimization.

## Understanding Context

### Context Window Size
- **Total Available**: 200,000 tokens
- **Effective With MCPs**: Can drop to 70,000 tokens
- **Critical Threshold**: < 80,000 tokens = degraded performance

### What Consumes Context

1. **System Prompts** (~5,000-15,000 tokens)
2. **Conversation History** (grows over time)
3. **File Contents** (when read)
4. **Tool Definitions** (MCP servers)
5. **Agent Context** (specialized agents)

## MCP Server Management

### The Problem
Each MCP (Model Context Protocol) server adds tools to Claude's context. Too many tools overwhelm the context window.

### Recommended Limits
- **Total MCPs**: 20-30 maximum
- **Enabled Per Project**: < 10
- **Active Tools**: < 80

### How to Manage MCPs

#### Project-Level Configuration
Create `.claude/config.json` in your project:

```json
{
  "disabledMcpServers": [
    "aws-mcp",
    "kubernetes-mcp",
    "terraform-mcp"
  ]
}
```

#### Global Configuration
Edit `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "filesystem": { "enabled": true },
    "github": { "enabled": true },
    "slack": { "enabled": false },
    "aws": { "enabled": false }
  }
}
```

#### Smart MCP Strategy

**Enable Only What You Need:**
- Web development? Enable: filesystem, github, npm
- Cloud work? Enable: aws, docker, kubernetes
- Data science? Enable: filesystem, python, jupyter

**Disable When Not Using:**
```bash
# Disable MCP temporarily
/mcp disable aws-mcp

# Re-enable when needed
/mcp enable aws-mcp

# List all MCPs
/mcp list
```

## Package Manager Detection

### Configuration Priority
Claude detects package managers in this order:

1. **Environment Variable**
   ```bash
   export CLAUDE_PACKAGE_MANAGER=pnpm
   ```

2. **Project Config**
   ```json
   // .claude/package-manager.json
   {
     "packageManager": "pnpm"
   }
   ```

3. **package.json**
   ```json
   {
     "packageManager": "pnpm@8.0.0"
   }
   ```

4. **Lock File Detection**
   - `pnpm-lock.yaml` → pnpm
   - `yarn.lock` → yarn
   - `package-lock.json` → npm
   - `bun.lockb` → bun

5. **Global Config**
   ```json
   // ~/.claude/package-manager.json
   {
     "packageManager": "npm"
   }
   ```

6. **First Available**
   - Checks: pnpm, yarn, bun, npm

### Setup Command
```bash
# Run this in your project
/setup-pm

# Or manually create config
echo '{"packageManager":"pnpm"}' > .claude/package-manager.json
```

## Context Optimization Strategies

### 1. Minimize File Reads

**Bad Approach:**
```typescript
// Reading entire large files
Read('src/components/LargeComponent.tsx')
Read('src/utils/helpers.ts')
Read('src/config/settings.ts')
```

**Better Approach:**
```typescript
// Use Grep to find specific code first
Grep('function targetFunction', { type: 'ts' })
// Then read only the relevant file
Read('src/utils/helpers.ts', { offset: 100, limit: 50 })
```

### 2. Use Agents Wisely

**Problem**: Spawning agents adds their context to yours

**Solution**: Use agents for expensive operations
```typescript
// Bad: Reading 50 files in main context
for (const file of allFiles) {
  Read(file);
}

// Good: Delegate to Explore agent
Task({
  subagent_type: 'Explore',
  prompt: 'Find all authentication-related functions'
});
```

### 3. Clear Unnecessary History

**When to Reset:**
- Switching to unrelated task
- Context getting too large
- Performance degrading

**How to Reset:**
```bash
# Start fresh conversation
/clear

# Or use checkpoint/save for important context
/save checkpoint-before-refactor
```

### 4. Optimize System Prompts

**Keep Custom Instructions Concise:**
```markdown
<!-- Bad: 5,000 tokens of instructions -->
- Always do X
- Never do Y
- Consider Z
[... 200 more rules ...]

<!-- Good: 500 tokens, focused -->
# Core Rules
1. Security: Validate all input
2. Quality: Test before commit
3. Style: Follow project patterns
```

### 5. Strategic File Grouping

**Bad: Many small reads**
```typescript
Read('types/user.ts')
Read('types/auth.ts')
Read('types/api.ts')
```

**Better: Use Glob**
```typescript
Glob('types/**/*.ts')
// Then read specific files as needed
```

## Token Budget Management

### Monitoring Usage
Claude shows token usage after each response:
```
Token usage: 25,000/200,000; 175,000 remaining
```

### Staying Under Budget

**Target Ranges:**
- **Healthy**: < 50,000 tokens used
- **Warning**: 50,000-100,000 tokens
- **Critical**: > 100,000 tokens

**When Critical:**
1. Finish current task
2. Start new conversation
3. Provide brief summary of context
4. Continue fresh

## Model Selection for Context

### When to Use Each Model

**Haiku (Fast, Small Context)**
- Simple tasks
- Quick operations
- File searches
- Running commands

```typescript
Task({
  model: 'haiku',
  prompt: 'List all TypeScript files'
})
```

**Sonnet (Balanced)**
- General development
- Code review
- Implementation
- Default choice

```typescript
Task({
  model: 'sonnet',
  prompt: 'Implement user authentication'
})
```

**Opus (Large Context, Deep Reasoning)**
- Complex architecture
- Critical decisions
- Large refactors
- System design

```typescript
Task({
  model: 'opus',
  prompt: 'Design microservices architecture'
})
```

## Context-Aware Workflows

### Pattern 1: Progressive Loading
```
1. Start with high-level search (Grep/Glob)
2. Identify relevant files
3. Read only necessary sections
4. Implement changes
```

### Pattern 2: Agent Delegation
```
1. Delegate research to Explore agent
2. Agent returns summary
3. Make decisions with minimal context
4. Implement with focused reads
```

### Pattern 3: Checkpoint Strategy
```
1. Complete Phase 1
2. Save checkpoint
3. Clear conversation
4. Resume with summary
5. Continue Phase 2
```

## Memory Persistence

### Session Hooks
Save and load context between sessions:

```json
// ~/.claude/settings.json
{
  "hooks": {
    "session:end": "~/.claude/hooks/save-context.sh",
    "session:start": "~/.claude/hooks/load-context.sh"
  }
}
```

**save-context.sh:**
```bash
#!/bin/bash
# Save important context to file
echo "$CONVERSATION_SUMMARY" > ~/.claude/memory/last-session.txt
```

**load-context.sh:**
```bash
#!/bin/bash
# Load previous context if relevant
if [ -f ~/.claude/memory/last-session.txt ]; then
  cat ~/.claude/memory/last-session.txt
fi
```

## Best Practices Summary

### Do ✅
- Monitor token usage regularly
- Disable unused MCPs
- Use agents for expensive operations
- Read files selectively
- Clear context when switching tasks
- Use appropriate model for task
- Keep custom instructions concise

### Don't ❌
- Enable all MCPs at once
- Read entire large files unnecessarily
- Keep irrelevant history
- Use Opus for simple tasks
- Let context grow unbounded
- Read files you don't need

## Troubleshooting

### Symptom: Slow Responses
**Cause**: Context too large
**Solution**:
1. Check token usage
2. Clear unnecessary history
3. Disable unused MCPs

### Symptom: "Context Limit Exceeded"
**Cause**: Too much content
**Solution**:
1. Start new conversation
2. Reduce MCP count
3. Read fewer files

### Symptom: Claude "Forgets" Earlier Info
**Cause**: Context window full
**Solution**:
1. Use memory persistence hooks
2. Save checkpoints
3. Provide brief summaries when resuming

## Advanced: Context Compression

### Technique 1: Summarization
```
# At context checkpoint
"Summarize the key decisions and code changes from this session"

# Use summary to start fresh
"Continuing from: [summary]. Now let's implement feature Y."
```

### Technique 2: Artifact Storage
```bash
# Save important info externally
echo "API endpoints: /api/users, /api/auth" > .claude/project-info.txt

# Reference when needed
"Check .claude/project-info.txt for endpoints"
```

### Technique 3: Continuous Learning
Extract patterns mid-session and save as skills:

```markdown
# .claude/skills/project-patterns.md
---
name: project-patterns
description: Common patterns used in this project
---

- API routes in /api directory
- Components use hooks pattern
- Error handling via ErrorBoundary
```

## Metrics to Track

Monitor these over time:
- Average tokens per session
- Number of active MCPs
- Files read per task
- Agent spawn frequency
- Session duration before reset

Optimize based on your workflow patterns.
