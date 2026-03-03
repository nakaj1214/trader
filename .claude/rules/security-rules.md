# Security Rules

These rules MUST be followed at all times when writing or reviewing code.

## 1. No Hardcoded Secrets

### Rule
NEVER hardcode secrets, credentials, API keys, or sensitive data in code.

### Violations
```typescript
// ❌ NEVER DO THIS
const API_KEY = "sk_live_abc123xyz789";
const DB_PASSWORD = "mypassword123";
const SECRET_TOKEN = "super-secret-token";
```

### Correct Approach
```typescript
// ✅ Use environment variables
const API_KEY = process.env.API_KEY;
const DB_PASSWORD = process.env.DB_PASSWORD;
const SECRET_TOKEN = process.env.SECRET_TOKEN;

// ✅ Validate they exist
if (!API_KEY) {
  throw new Error('API_KEY environment variable is required');
}
```

### Detection
- Scan for patterns: `password`, `secret`, `key`, `token`, `api_key`
- Check for credential-like strings in assignments
- Verify .env files are in .gitignore

## 2. Input Validation

### Rule
ALL user input MUST be validated before processing.

### Requirements
- Validate type
- Validate format
- Validate length
- Validate range
- Sanitize for special characters

### Examples
```typescript
// ❌ No validation
function createUser(email: string, age: number) {
  db.query(`INSERT INTO users (email, age) VALUES ('${email}', ${age})`);
}

// ✅ Proper validation
function createUser(email: string, age: number) {
  // Type validation
  if (typeof email !== 'string' || typeof age !== 'number') {
    throw new ValidationError('Invalid types');
  }

  // Format validation
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(email)) {
    throw new ValidationError('Invalid email format');
  }

  // Range validation
  if (age < 0 || age > 150) {
    throw new ValidationError('Invalid age range');
  }

  // Length validation
  if (email.length > 255) {
    throw new ValidationError('Email too long');
  }

  // Use parameterized queries
  db.query('INSERT INTO users (email, age) VALUES (?, ?)', [email, age]);
}
```

## 3. SQL Injection Prevention

### Rule
ALWAYS use parameterized queries or ORMs. NEVER concatenate user input into SQL.

### Violations
```typescript
// ❌ SQL Injection vulnerability
const query = `SELECT * FROM users WHERE id = ${userId}`;
const query = `SELECT * FROM users WHERE name = '${userName}'`;
db.execute(query);
```

### Correct Approach
```typescript
// ✅ Parameterized query
db.query('SELECT * FROM users WHERE id = ?', [userId]);

// ✅ Using ORM
await User.findOne({ where: { id: userId } });

// ✅ Named parameters
db.query('SELECT * FROM users WHERE name = :name', { name: userName });
```

## 4. XSS Prevention

### Rule
Escape all user-generated content before rendering in HTML.

### Violations
```typescript
// ❌ XSS vulnerability
function displayComment(comment: string) {
  return `<div>${comment}</div>`;
}
```

### Correct Approach
```typescript
// ✅ Escape HTML
function escapeHtml(text: string): string {
  const map: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  };
  return text.replace(/[&<>"']/g, m => map[m]);
}

function displayComment(comment: string) {
  return `<div>${escapeHtml(comment)}</div>`;
}

// ✅ Use framework built-ins (React)
function Comment({ text }: { text: string }) {
  return <div>{text}</div>; // React auto-escapes
}
```

## 5. Authentication & Authorization

### Rule
- Passwords MUST be hashed with bcrypt or argon2
- Session tokens MUST be cryptographically random
- Authorization checks MUST occur on every request
- Rate limiting MUST be implemented

### Password Hashing
```typescript
// ❌ Plaintext or weak hashing
const password = userInput;
const hash = md5(password); // WEAK
const hash = sha1(password); // WEAK

// ✅ Proper hashing
import bcrypt from 'bcrypt';

const saltRounds = 12;
const hash = await bcrypt.hash(password, saltRounds);

// Verification
const isValid = await bcrypt.compare(inputPassword, storedHash);
```

### Session Management
```typescript
// ✅ Secure session token generation
import crypto from 'crypto';

function generateSessionToken(): string {
  return crypto.randomBytes(32).toString('hex');
}

// ✅ Session configuration
app.use(session({
  secret: process.env.SESSION_SECRET,
  resave: false,
  saveUninitialized: false,
  cookie: {
    secure: true,      // HTTPS only
    httpOnly: true,    // No JavaScript access
    sameSite: 'strict', // CSRF protection
    maxAge: 3600000    // 1 hour
  }
}));
```

### Authorization
```typescript
// ✅ Check on every protected route
function requireAuth(req, res, next) {
  if (!req.session.userId) {
    return res.status(401).json({ error: 'Unauthorized' });
  }
  next();
}

function requireRole(role: string) {
  return (req, res, next) => {
    if (req.user.role !== role) {
      return res.status(403).json({ error: 'Forbidden' });
    }
    next();
  };
}

app.get('/admin', requireAuth, requireRole('admin'), handler);
```

## 6. Command Injection Prevention

### Rule
NEVER execute shell commands with unsanitized user input.

### Violations
```typescript
// ❌ Command injection vulnerability
exec(`convert ${userFileName} output.jpg`);
```

### Correct Approach
```typescript
// ✅ Validate and sanitize
function sanitizeFileName(fileName: string): string {
  // Only allow alphanumeric, dots, and hyphens
  return fileName.replace(/[^a-zA-Z0-9.-]/g, '');
}

const safeFileName = sanitizeFileName(userFileName);
exec(`convert ${safeFileName} output.jpg`);

// ✅ Better: Use libraries instead of shell commands
import sharp from 'sharp';
await sharp(userFileName).toFile('output.jpg');

// ✅ Best: Use spawn with array args (no shell interpolation)
import { spawn } from 'child_process';
spawn('convert', [userFileName, 'output.jpg']);
```

## 7. Path Traversal Prevention

### Rule
Validate file paths to prevent directory traversal attacks.

### Violations
```typescript
// ❌ Path traversal vulnerability
app.get('/file/:name', (req, res) => {
  const filePath = `./uploads/${req.params.name}`;
  res.sendFile(filePath);
});
// Attacker could use: /file/../../etc/passwd
```

### Correct Approach
```typescript
// ✅ Validate path
import path from 'path';

app.get('/file/:name', (req, res) => {
  const uploadsDir = path.resolve('./uploads');
  const filePath = path.resolve(uploadsDir, req.params.name);

  // Ensure path is within uploads directory
  if (!filePath.startsWith(uploadsDir)) {
    return res.status(403).json({ error: 'Forbidden' });
  }

  res.sendFile(filePath);
});
```

## 8. CSRF Protection

### Rule
Implement CSRF tokens for state-changing operations.

### Implementation
```typescript
// ✅ CSRF protection middleware
import csrf from 'csurf';

const csrfProtection = csrf({ cookie: true });

app.get('/form', csrfProtection, (req, res) => {
  res.render('form', { csrfToken: req.csrfToken() });
});

app.post('/submit', csrfProtection, (req, res) => {
  // Process form
});

// ✅ In HTML
<form method="POST">
  <input type="hidden" name="_csrf" value="{{csrfToken}}">
  <!-- form fields -->
</form>
```

## 9. Secure Headers

### Rule
Always set security headers.

### Implementation
```typescript
// ✅ Using helmet.js
import helmet from 'helmet';

app.use(helmet());

// ✅ Manual configuration
app.use((req, res, next) => {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-Frame-Options', 'DENY');
  res.setHeader('X-XSS-Protection', '1; mode=block');
  res.setHeader('Strict-Transport-Security', 'max-age=31536000; includeSubDomains');
  res.setHeader('Content-Security-Policy', "default-src 'self'");
  next();
});
```

## 10. Error Handling

### Rule
Don't expose sensitive information in error messages.

### Violations
```typescript
// ❌ Information leakage
catch (err) {
  res.status(500).json({
    error: err.message,
    stack: err.stack,
    query: sql
  });
}
```

### Correct Approach
```typescript
// ✅ Safe error handling
catch (err) {
  // Log detailed error server-side
  logger.error('Database error', {
    error: err,
    query: sql,
    user: req.user.id
  });

  // Send generic error to client
  res.status(500).json({
    error: 'An error occurred while processing your request'
  });
}
```

## Security Checklist

Before committing code, verify:

- [ ] No hardcoded secrets or credentials
- [ ] All user input is validated
- [ ] SQL queries are parameterized
- [ ] HTML output is escaped
- [ ] Passwords are properly hashed (bcrypt/argon2)
- [ ] Authentication is enforced on protected routes
- [ ] Authorization checks are in place
- [ ] No command injection vulnerabilities
- [ ] File paths are validated
- [ ] CSRF protection is implemented
- [ ] Security headers are set
- [ ] Error messages don't leak information
- [ ] Rate limiting is implemented
- [ ] HTTPS is enforced in production
- [ ] Dependencies are up to date

## Automatic Checks

These should be automated in CI/CD:

```bash
# Dependency vulnerability scanning
npm audit

# Static analysis
npm run lint:security

# Secret scanning
git-secrets --scan

# License compliance
npm run license-check
```

## When to Escalate

Immediately escalate to security team if:
- Potential data breach discovered
- Authentication bypass found
- Privilege escalation possible
- Secrets committed to repository
- Production credentials exposed
