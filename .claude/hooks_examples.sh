#!/bin/bash

# Claude Code Hooks Examples
# These hooks can be configured in your Claude settings to automate tasks

# ============================================================================
# PRE-COMMIT HOOK
# Runs before git commit operations
# ============================================================================

# Example: Run linting before commits
if [ "$HOOK_TYPE" = "pre-commit" ]; then
  echo "Running linter..."
  npm run lint || exit 1
fi

# Example: Run tests before commits
if [ "$HOOK_TYPE" = "pre-commit" ]; then
  echo "Running tests..."
  npm test || exit 1
fi

# Example: Format code before commits
if [ "$HOOK_TYPE" = "pre-commit" ]; then
  echo "Formatting code..."
  npm run format
fi

# ============================================================================
# POST-TOOL HOOK
# Runs after specific tool calls
# ============================================================================

# Example: Auto-format after file edits
if [ "$TOOL_NAME" = "Edit" ] || [ "$TOOL_NAME" = "Write" ]; then
  echo "Auto-formatting edited file..."
  npx prettier --write "$FILE_PATH"
fi

# Example: Run type checking after TypeScript edits
if [ "$TOOL_NAME" = "Edit" ] && [[ "$FILE_PATH" == *.ts ]]; then
  echo "Type checking..."
  npx tsc --noEmit "$FILE_PATH"
fi

# Example: Validate JSON after editing config files
if [[ "$FILE_PATH" == *.json ]]; then
  echo "Validating JSON..."
  jq empty "$FILE_PATH" || {
    echo "Invalid JSON detected!"
    exit 1
  }
fi

# ============================================================================
# USER PROMPT SUBMIT HOOK
# Runs when user submits a message
# ============================================================================

# Example: Log all user prompts for later analysis
if [ "$HOOK_TYPE" = "user-prompt-submit" ]; then
  echo "[$(date)] User: $USER_MESSAGE" >> ~/claude_logs/prompts.log
fi

# Example: Validate prompt length
if [ ${#USER_MESSAGE} -gt 10000 ]; then
  echo "Warning: Very long prompt detected (${#USER_MESSAGE} chars)"
fi

# ============================================================================
# BASH EXECUTION HOOK
# Runs before bash commands execute
# ============================================================================

# Example: Prevent dangerous commands
if [[ "$BASH_COMMAND" == *"rm -rf /"* ]]; then
  echo "BLOCKED: Dangerous command detected!"
  exit 1
fi

# Example: Require confirmation for production deployments
if [[ "$BASH_COMMAND" == *"deploy --prod"* ]]; then
  read -p "Deploy to production? (y/n) " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
  fi
fi

# ============================================================================
# FILE CHANGE HOOK
# Runs when files are modified
# ============================================================================

# Example: Invalidate cache when dependencies change
if [[ "$FILE_PATH" == "package.json" ]]; then
  echo "Dependencies changed, clearing cache..."
  rm -rf node_modules/.cache
fi

# Example: Update documentation when API changes
if [[ "$FILE_PATH" == *"/api/"* ]]; then
  echo "API changed, regenerating docs..."
  npm run docs:generate
fi
