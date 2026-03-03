# Claude Agent Usage Guide

## Overview
Claude Code provides specialized agents for different tasks. Using the right agent significantly improves performance and accuracy.

## Available Agents

### 1. Explore Agent
**Use for:** Codebase exploration and understanding

**When to use:**
- "Where are errors handled?"
- "How does authentication work?"
- "What is the codebase structure?"
- "Find all components that use hooks"
- Any exploration that requires multiple searches

**Example:**
```
User: Where are errors from the client handled?
Assistant: [Uses Task tool with subagent_type=Explore]
```

**Thoroughness levels:**
- `quick`: Basic searches
- `medium`: Moderate exploration (default)
- `very thorough`: Comprehensive analysis

### 2. Plan Agent
**Use for:** Designing implementation strategies

**When to use:**
- Complex feature implementation
- Multiple valid approaches exist
- Architectural decisions needed
- Multi-file changes required

**What it does:**
- Explores codebase thoroughly
- Identifies critical files
- Considers trade-offs
- Creates step-by-step plan

### 3. Bash Agent
**Use for:** Command-line operations

**When to use:**
- Git operations
- Package management (npm, pip, etc.)
- Docker commands
- Build processes
- Any terminal operations

**NOT for:**
- File reading (use Read tool)
- File editing (use Edit tool)
- File searching (use Glob/Grep tools)

### 4. General-Purpose Agent
**Use for:** Complex multi-step tasks

**When to use:**
- Research requiring multiple steps
- Tasks combining several operations
- Open-ended searches
- Complex data gathering

## Agent Best Practices

### Parallel Execution
Launch multiple agents concurrently when possible:
```javascript
// Good: Single message with multiple agents
Task(agent1), Task(agent2), Task(agent3)

// Bad: Sequential agent launches
Task(agent1) -> wait -> Task(agent2) -> wait -> Task(agent3)
```

### Background Execution
For long-running tasks:
```javascript
Task(subagent_type="Bash",
     prompt="Run comprehensive test suite",
     run_in_background=true)
```

### Model Selection
Choose appropriate model for task complexity:
```javascript
// Quick task - use Haiku
Task(model="haiku", prompt="List all .ts files")

// Complex reasoning - use Opus
Task(model="opus", prompt="Design authentication architecture")

// Default - Sonnet for balanced performance
Task(prompt="Implement feature X")
```

### Agent Resumption
Resume previous agents to continue work:
```javascript
// First call
agent_id = Task(subagent_type="Explore", prompt="Find auth code")

// Later, resume with same context
Task(resume=agent_id, prompt="Now check error handling")
```

## Common Patterns

### Pattern 1: Explore Then Implement
```
1. Task(Explore): "Find authentication implementation"
2. Review findings
3. EnterPlanMode: Design changes
4. Implement changes
```

### Pattern 2: Parallel Research
```
Task(Explore, "How is routing handled?")
Task(Explore, "How is state managed?")
Task(Explore, "How are API calls made?")
// All run in parallel
```

### Pattern 3: Build and Test
```
1. Make code changes
2. Task(Bash): "npm run build"
3. Task(Bash): "npm test"
4. Fix any issues found
```

### Pattern 4: Comprehensive Analysis
```
Task(subagent_type="Explore",
     thoroughness="very thorough",
     prompt="Analyze entire authentication flow including error handling, session management, and security measures")
```

## Anti-Patterns

❌ **Using Bash for file operations**
```
// Bad
Task(Bash, "cat src/index.ts")
// Good
Read("src/index.ts")
```

❌ **Not using Explore for codebase questions**
```
// Bad
Grep + Glob + Read manually
// Good
Task(Explore, "Where is feature X implemented?")
```

❌ **Sequential agents when parallel is possible**
```
// Bad
agent1 -> wait -> agent2 -> wait
// Good
agent1, agent2 in same message
```

❌ **Wrong model for task complexity**
```
// Bad
Task(model="opus", "List files")
// Good
Task(model="haiku", "List files")
```

## Decision Tree

```
Is it codebase exploration? → Explore Agent
  ├─ Simple keyword search → quick
  ├─ Moderate investigation → medium
  └─ Comprehensive analysis → very thorough

Is it implementation planning? → Plan Agent

Is it terminal command? → Bash Agent
  └─ But NOT for file operations

Is it multi-step research? → General-Purpose Agent

Is it file operation?
  ├─ Reading → Read tool (NOT agent)
  ├─ Editing → Edit tool (NOT agent)
  └─ Searching → Glob/Grep tools (NOT agent)
```

## Performance Tips

1. **Use Task tool for expensive operations** to reduce context usage
2. **Launch agents in parallel** when tasks are independent
3. **Use background execution** for long-running operations
4. **Choose right model**: Haiku for simple, Opus for complex
5. **Resume agents** instead of starting fresh when continuing work
6. **Be specific in prompts** to help agents work efficiently

## When NOT to Use Agents

- Reading a specific known file → Use Read tool
- Editing a specific line → Use Edit tool
- Finding files by name pattern → Use Glob tool
- Searching for specific text → Use Grep tool
- Running single command → Use Bash tool directly
