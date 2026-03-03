# Common Coding Style Rules

Applies to all languages and file types.

## Immutability (Critical)

**ALWAYS create new objects, NEVER mutate existing ones.**

```typescript
// ❌ Bad - mutates existing object
user.name = newName;

// ✅ Good - creates new object
return { ...user, name: newName };
```

Prevents hidden side effects and enables safe concurrency.

## File Organization

- Target **200-400 lines** per file; hard ceiling at **800 lines**
- Prefer numerous focused files over large monolithic ones
- Structure by **feature or domain**, not by file type

## Error Handling

**ALWAYS handle errors comprehensively:**
- Explicit handling at each level
- User-friendly UI messages (don't expose internals)
- Detailed server-side logging
- Never silent failures (`catch (e) {}` is forbidden)

## Input Validation

**ALWAYS validate at system boundaries:**
- All user input
- External API responses
- File content before processing
- Use schema-based validation (Zod, Pydantic, etc.)

## Code Quality Checklist

Before marking work complete, verify:
- [ ] Naming is clear and self-documenting
- [ ] Functions are under 50 lines
- [ ] Files are under 800 lines
- [ ] Nesting depth is max 4 levels
- [ ] All errors are handled
- [ ] No hardcoded values (use config/constants)
- [ ] Immutable patterns used throughout
