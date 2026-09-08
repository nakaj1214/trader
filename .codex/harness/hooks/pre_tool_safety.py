#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SAFE_WRAPPER = ".codex/harness/scripts/safe_test.py"

TEST_PATTERNS = (
    re.compile(r"\bphp\s+(?:-[^\s]+\s+)*artisan\s+test\b", re.I),
    re.compile(r"(?:^|[\s;&|])(?:\./)?vendor/bin/(?:phpunit|pest)\b", re.I),
    re.compile(r"(?:^|[\s;&|])(?:phpunit|pest)\b", re.I),
)

DANGEROUS_PATTERNS = (
    (re.compile(r"\bphp\s+artisan\s+migrate(?:\s|$)", re.I), "persistent migration"),
    (re.compile(r"\bphp\s+artisan\s+(?:migrate:fresh|migrate:refresh|migrate:reset|migrate:rollback|db:wipe|db:seed)\b", re.I), "destructive/persistent Artisan DB command"),
    (re.compile(r"\b(?:DROP\s+(?:TABLE|DATABASE)|TRUNCATE\s+(?:TABLE\s+)?|ALTER\s+TABLE|RENAME\s+TABLE)\b", re.I), "destructive SQL"),
    (re.compile(r"\bphp\s+artisan\s+(?:queue:work|queue:listen|queue:restart|schedule:run|schedule:work|horizon)\b", re.I), "scheduler/queue worker execution"),
    (re.compile(r"(?:^|[;&|]\s*)(?:sudo\s+)?(?:lp|lpr|cancel|lpadmin|cupsenable|cupsdisable)\b", re.I), "printer/CUPS mutation"),
    (re.compile(r"(?:^|[;&|]\s*)(?:sudo\s+)?(?:sendmail|mail|mailx)\b", re.I), "real mail submission"),
    (re.compile(r"\bcurl\b[^\n;&|]*(?:-X|--request)\s*(?:POST|PUT|PATCH|DELETE)\b", re.I), "external HTTP write"),
    (re.compile(r"\bcurl\b[^\n;&|]*(?:--data(?:-raw|-binary|-urlencode)?|-d|-F|--form|--upload-file|-T)\b", re.I), "external HTTP upload/write"),
    (re.compile(r"\bwget\b[^\n;&|]*(?:--post-data|--post-file|--method\s*=\s*(?:POST|PUT|PATCH|DELETE))", re.I), "external HTTP write"),
    (re.compile(r"(?:^|[;&|]\s*)(?:scp|sftp)\b", re.I), "remote file transfer"),
    (re.compile(r"\brsync\b[^\n;&|]*(?:\w+@[\w.-]+:|[\w.-]+:[^/])", re.I), "remote rsync transfer"),
    (re.compile(r"\bsmbclient\b[^\n;&|]*(?:-c\s+)?['\"][^'\"]*\b(?:put|mput|del|rm|rename|mkdir|rmdir)\b", re.I), "SMB/NAS write"),
    (re.compile(r"(?:^|[;&|]\s*)\s*(?:sudo\s+)?rm\s+-[^\n;&|]*r[^\n;&|]*(?:f[^\n;&|]*)?\s+", re.I), "recursive filesystem deletion"),
    (re.compile(r"\bfind\b[^\n;&|]*\s-delete\b", re.I), "recursive filesystem deletion"),
    (re.compile(r"(?:^|[;&|]\s*)\s*(?:sudo\s+)?shred\b", re.I), "destructive file overwrite"),
    (re.compile(r"\bdd\b[^\n;&|]*\bof=", re.I), "raw file/device overwrite"),
    (re.compile(r"\bgit\s+reset\s+--hard\b", re.I), "destructive Git reset"),
    (re.compile(r"\bgit\s+clean\b", re.I), "destructive Git clean"),
    (re.compile(r"\bgit\s+(?:checkout|restore)\s+--?\s*(?:\.|:/)", re.I), "bulk Git worktree overwrite"),
    (re.compile(r"\bgit\s+push\b[^\n;&|]*(?:--force|-f)\b", re.I), "force Git push"),
    (re.compile(r"docker\s+(?:compose\s+)?down\b[^\n;&|]*\s(?:-v|--volumes)\b", re.I), "Docker volume deletion"),
    (re.compile(r"docker\s+(?:volume|system|container)\s+(?:rm|prune)\b", re.I), "Docker persistent cleanup"),
)

WRITE_SQL = re.compile(r"\b(?:INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|CREATE\s+(?:TABLE|DATABASE)|DROP\s+(?:TABLE|DATABASE)|TRUNCATE|ALTER\s+TABLE)\b", re.I)
DB_CLIENT_CMD = re.compile(
    r"(?:^|[;&|]\s*)(?:sudo\s+)?(?:mysql|mariadb|psql|sqlite3)\b"
    r"|\bdocker\s+(?:compose\s+)?exec\b[^\n;&|]*\s(?:mysql|mariadb|psql|sqlite3)\b",
    re.I,
)
TINKER = re.compile(r"\bartisan\s+tinker\b", re.I)
SMBCLIENT = re.compile(r"(?:^|[;&|]\s*)(?:sudo\s+)?smbclient\b", re.I)
CUSTOM_WRITE_ARTISAN = re.compile(r"\bphp\s+artisan\s+[^\s;&|]*(?:migrate|import|restore|repair|purge|delete|cleanup|seed|sync)[^\s;&|]*", re.I)

SMB_READ_ONLY_VERBS = {"ls", "dir", "stat", "allinfo", "pwd", "cd", "help", "?", "quit", "exit"}

def smbclient_is_bounded_read_only(command: str) -> bool:
    """Allow only non-interactive smbclient -c scripts composed of read/navigation verbs."""
    m = re.search(r"\bsmbclient\b.*?\s-c\s+(?:'([^']*)'|\"([^\"]*)\")", command, re.I)
    if not m:
        return False
    script = m.group(1) if m.group(1) is not None else m.group(2)
    if script is None:
        return False
    for statement in script.split(';'):
        statement = statement.strip()
        if not statement:
            continue
        verb = statement.split(None, 1)[0].lower()
        if verb not in SMB_READ_ONLY_VERBS:
            return False
    return True

PROTECTED_PATHS = (
    ".codex/harness/hooks/pre_tool_safety.py",
    ".codex/harness/scripts/test_db_guard.py",
    ".codex/harness/scripts/side_effect_guard.py",
    ".codex/harness/scripts/safe_test.py",
    ".codex/harness/scripts/verify.py",
    ".codex/harness/v6_4_policy.json",
    ".codex/hooks.json",
    ".codex/rules/harness-side-effect-safety.rules",
    "tests/concerns/harnesssideeffectisolation.php",
)

def deny(reason: str) -> int:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }, ensure_ascii=False))
    return 0

def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    if not isinstance(command, str) or not command.strip():
        return 0
    low = command.lower()

    if tool_name == "apply_patch":
        if any(path in low for path in PROTECTED_PATHS):
            return deny("Adaptive Harness v6.4 blocked an agent edit to side-effect safety infrastructure. Update the Harness through its installer.")
        if "@harness-side-effect-allow" in low:
            return deny("Adaptive Harness v6.4 blocked adding a side-effect bypass marker. A human must review and add any exceptional allow marker outside the agent.")
        if "phpunit.xml" in low:
            if re.search(r"^\+.*(?:DB_CONNECTION|MAIL_MAILER|QUEUE_CONNECTION|FILESYSTEM_DISK|HTTP_PROXY|CUPS_SERVER).*(?:mysql|smtp|redis|sqs|s3|production|prod)", command, re.I | re.M):
                return deny("Adaptive Harness v6.4 blocked a phpunit.xml edit that could reconnect tests to persistent/external infrastructure.")
            if re.search(r"^-.*(?:APP_ENV|DB_CONNECTION|DB_DATABASE|MAIL_MAILER|QUEUE_CONNECTION|CACHE_STORE|SESSION_DRIVER|FILESYSTEM_DISK|BROADCAST_CONNECTION|CUPS_SERVER|HTTP_PROXY|HTTPS_PROXY|ALL_PROXY).*force=[\"']true[\"']", command, re.I | re.M):
                return deny("Adaptive Harness v6.4 blocked removal of forced test isolation settings.")
        if "tests/testcase.php" in low and re.search(r"^-.*(?:HarnessSideEffectIsolation|harnessEnableSideEffectIsolation|environment\(['\"]testing|:memory:|DB::purge|database\.connections)", command, re.I | re.M):
            return deny("Adaptive Harness v6.4 blocked removal of the Laravel TestCase isolation guard.")
        return 0

    if tool_name not in ("Bash", "shell_command", "exec_command", None):
        return 0

    if SAFE_WRAPPER in low:
        return 0

    if any(path in low for path in PROTECTED_PATHS) and re.search(
        r"(?:\brm\b|\bmv\b|sed\s+-i|perl\s+-pi|\btruncate\b|(?:>|>>)\s*[^ ]|\btee\b)",
        command,
        re.I,
    ):
        return deny("Adaptive Harness v6.4 blocked a shell command that could modify/remove safety infrastructure.")

    for rx, label in DANGEROUS_PATTERNS:
        if rx.search(command):
            return deny(
                f"Adaptive Harness v6.4 blocked {label}. This is an external, destructive, or persistent side effect, "
                "not routine autonomous verification. Use read-only diagnostics or a separately reviewed user-supervised procedure."
            )

    if TINKER.search(command) and not re.search(r"--execute(?:=|\s)", command, re.I):
        return deny("Adaptive Harness v6.4 blocked interactive Laravel Tinker. Use a bounded non-interactive read-only `tinker --execute=...` probe.")
    if DB_CLIENT_CMD.search(command) and not re.search(r"(?:^|\s)(?:-e|--execute(?:=|\s)|-c)(?:\s|=)", command, re.I):
        return deny("Adaptive Harness v6.4 blocked an interactive database client. Use a non-interactive read-only SELECT/SHOW/DESCRIBE/EXPLAIN command.")
    if SMBCLIENT.search(command) and not smbclient_is_bounded_read_only(command):
        return deny("Adaptive Harness v6.4 blocked interactive/non-read-only smbclient. Use a bounded `-c 'ls'` / metadata-only command containing read/navigation verbs only.")

    if (DB_CLIENT_CMD.search(command) or TINKER.search(command) or re.search(r"\bphp\s+-r\b", command, re.I)) and WRITE_SQL.search(command):
        return deny("Adaptive Harness v6.4 blocked a database write/destructive command before execution.")
    if TINKER.search(command) and re.search(r"(?:->|::)(?:delete|forceDelete|update|insert|insertGetId|upsert|create|firstOrCreate|updateOrCreate|save|restore|truncate|drop|dropIfExists|statement|unprepared)\s*\(", command, re.I):
        return deny("Adaptive Harness v6.4 blocked a Laravel tinker write/destructive call.")
    if CUSTOM_WRITE_ARTISAN.search(command) and not re.search(r"\b(?:status|check|show|list|dry-run|pretend)\b", command, re.I):
        return deny("Adaptive Harness v6.4 blocked a custom Artisan command whose name suggests persistent mutation.")

    root = Path(payload.get("cwd") or ".").resolve()
    laravel = (root / "artisan").exists() or (root / "src" / "artisan").exists()
    if laravel and any(rx.search(command) for rx in TEST_PATTERNS):
        return deny(
            "Adaptive Harness v6.4 blocked a raw Laravel/PHP test command. Use "
            "`python3 .codex/harness/scripts/safe_test.py --shell '<command>'` so DB and external side effects are isolated first."
        )

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
