#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DB_GUARD = ROOT / ".codex" / "harness" / "scripts" / "test_db_guard.py"
SIDE_GUARD = ROOT / ".codex" / "harness" / "scripts" / "side_effect_guard.py"

DANGEROUS = (
    re.compile(r"\bartisan\s+(?:migrate(?::fresh|:refresh|:reset|:rollback)?|db:wipe|db:seed)\b", re.I),
    re.compile(r"\bDROP\s+(?:TABLE|DATABASE)\b", re.I),
    re.compile(r"\bTRUNCATE\s+(?:TABLE\s+)?", re.I),
    re.compile(r"\bartisan\s+(?:queue:work|queue:listen|queue:restart|schedule:run|schedule:work|horizon)\b", re.I),
    re.compile(r"(?:^|[\s;&|])(?:lp|lpr|cancel|lpadmin|cupsenable|cupsdisable)\b", re.I),
    re.compile(r"docker\s+(?:compose\s+)?down\b[^\n;&|]*\s(?:-v|--volumes)\b", re.I),
    re.compile(r"docker\s+(?:volume|system|container)\s+(?:rm|prune)\b", re.I),
)

TEST_PATTERNS = (
    re.compile(r"\bphp\s+(?:-[^\s]+\s+)*artisan\s+test\b", re.I),
    re.compile(r"(?:^|[\s;&|])(?:\./)?vendor/bin/(?:phpunit|pest)\b", re.I),
    re.compile(r"(?:^|[\s;&|])(?:phpunit|pest)\b", re.I),
)

EXTRA_SIDE_EFFECTS = (
    re.compile(r"\bcurl\b[^\n;&|]*(?:-X|--request)\s*(?:POST|PUT|PATCH|DELETE)\b", re.I),
    re.compile(r"\bcurl\b[^\n;&|]*(?:--data(?:-raw|-binary|-urlencode)?|-d|-F|--form|--upload-file|-T)\b", re.I),
    re.compile(r"\bwget\b[^\n;&|]*(?:--post-data|--post-file|--method\s*=\s*(?:POST|PUT|PATCH|DELETE))", re.I),
    re.compile(r"(?:^|[;&|]\s*)(?:scp|sftp)\b", re.I),
    re.compile(r"\bsmbclient\b[^\n;&|]*\b(?:put|mput|del|rm|rename|mkdir|rmdir)\b", re.I),
    re.compile(r"(?:^|[;&|]\s*)\s*(?:sudo\s+)?rm\s+-[^\n;&|]*r", re.I),
    re.compile(r"\bfind\b[^\n;&|]*\s-delete\b", re.I),
    re.compile(r"\bgit\s+(?:reset\s+--hard|clean\b|push\b[^\n;&|]*(?:--force|-f))", re.I),
)

PHP_DISABLED_FUNCTIONS = ",".join((
    "exec", "shell_exec", "system", "passthru", "proc_open", "popen",
    "curl_exec", "curl_multi_exec", "fsockopen", "pfsockopen", "stream_socket_client",
    "mail",
    "smbclient_state_new", "smbclient_state_init", "smbclient_open", "smbclient_unlink",
    "smbclient_rename", "smbclient_mkdir", "smbclient_rmdir", "smbclient_write",
))

TEST_ENV = {
    "ADAPTIVE_HARNESS_ROOT": str(ROOT / ".harness"),
    "ADAPTIVE_HARNESS_RUNTIME": str(ROOT / ".harness" / "runtime"),
    "APP_ENV": "testing",
    "DB_CONNECTION": "sqlite",
    "DB_DATABASE": ":memory:",
    "DB_HOST": "127.0.0.1",
    "DB_PORT": "1",
    "DB_USERNAME": "__harness_test_blocked__",
    "DB_PASSWORD": "__harness_test_blocked__",
    "DB_URL": "",
    "MAIL_MAILER": "array",
    "MAIL_HOST": "127.0.0.1",
    "MAIL_PORT": "1",
    "QUEUE_CONNECTION": "sync",
    "CACHE_STORE": "array",
    "SESSION_DRIVER": "array",
    "FILESYSTEM_DISK": "local",
    "BROADCAST_CONNECTION": "log",
    "BROADCAST_DRIVER": "log",
    "CUPS_SERVER": "127.0.0.1:1",
    "HTTP_PROXY": "http://127.0.0.1:1",
    "HTTPS_PROXY": "http://127.0.0.1:1",
    "ALL_PROXY": "http://127.0.0.1:1",
    "NO_PROXY": "",
    "http_proxy": "http://127.0.0.1:1",
    "https_proxy": "http://127.0.0.1:1",
    "all_proxy": "http://127.0.0.1:1",
    "no_proxy": "",
    "AWS_ACCESS_KEY_ID": "__harness_test_blocked__",
    "AWS_SECRET_ACCESS_KEY": "__harness_test_blocked__",
    "AWS_SESSION_TOKEN": "__harness_test_blocked__",
    "AWS_EC2_METADATA_DISABLED": "true",
    "REDIS_HOST": "127.0.0.1",
    "REDIS_PORT": "1",
    "MEMCACHED_HOST": "127.0.0.1",
    "MEMCACHED_PORT": "1",
}

def harden_php_invocation(cmd: str) -> str:
    ini = f"-d disable_functions={shlex.quote(PHP_DISABLED_FUNCTIONS)}"

    cmd = re.sub(
        r"\bphp\s+(?!-d\s+disable_functions=)artisan\s+test\b",
        lambda m: f"php {ini} artisan test",
        cmd,
        count=1,
        flags=re.I,
    )

    cmd = re.sub(
        r"\bphp\s+(?!-d\s+disable_functions=)((?:\./)?vendor/bin/(?:phpunit|pest))\b",
        lambda m: f"php {ini} {m.group(1)}",
        cmd,
        count=1,
        flags=re.I,
    )

    if not re.search(r"\bphp\s+-d\s+disable_functions=", cmd, re.I):
        cmd = re.sub(
            r"(?<![\w/])((?:\./)?vendor/bin/(?:phpunit|pest))\b",
            lambda m: f"php {ini} {m.group(1)}",
            cmd,
            count=1,
            flags=re.I,
        )

    return cmd

def inject_docker_env(cmd: str) -> str:
    opts = " ".join(f"-e {shlex.quote(k + '=' + v)}" for k, v in TEST_ENV.items())
    patterns = (
        re.compile(r"(\bdocker\s+compose(?:\s+--env-file\s+\S+)?\s+exec\b)", re.I),
        re.compile(r"(\bdocker-compose\s+exec\b)", re.I),
    )
    for rx in patterns:
        if rx.search(cmd):
            return rx.sub(lambda m: m.group(1) + " " + opts, cmd, count=1)
    return cmd

def run_guard(path: Path) -> int:
    if not path.exists():
        print(f"[SAFE-TEST:BLOCK] missing guard: {path.name}", file=sys.stderr)
        return 2
    return subprocess.run([sys.executable, str(path), "--quiet"], cwd=ROOT).returncode

def validate_test_command(cmd: str) -> str | None:
    if not any(rx.search(cmd) for rx in TEST_PATTERNS):
        return "safe_test.py only accepts Laravel/PHP test commands"

    if any(rx.search(cmd) for rx in DANGEROUS + EXTRA_SIDE_EFFECTS):
        return "test command contains a persistent/external side-effect operation"

    # Refuse command chaining. Quoted regex filters such as '(A|B)' remain a single shlex word.
    lexer = shlex.shlex(cmd, posix=True, punctuation_chars=";&|")
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return "test command has invalid shell quoting"
    if any(tok in {";", "&&", "||", "|", "&"} for tok in tokens):
        return "safe_test.py accepts one test command only; shell chaining/pipelines are blocked"
    if re.search(r"(?<![<])(?:>|>>|<)\\s*\\S", cmd):
        return "shell redirection is blocked in safe_test.py"

    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Run Laravel/PHP tests only after DB and side-effect isolation audits pass")
    ap.add_argument("--shell", required=True, help="Original test command string")
    args = ap.parse_args()
    cmd = args.shell

    problem = validate_test_command(cmd)
    if problem:
        print(f"[SAFE-TEST:BLOCK] {problem}", file=sys.stderr)
        return 2

    for guard in (DB_GUARD, SIDE_GUARD):
        rc = run_guard(guard)
        if rc != 0:
            return rc

    hardened = inject_docker_env(harden_php_invocation(cmd))
    env = os.environ.copy()
    env.update(TEST_ENV)
    print("[SAFE-TEST] DB + side-effect guards passed; running isolated test command")
    return subprocess.run(hardened, cwd=ROOT, env=env, shell=True, executable="/bin/bash").returncode

if __name__ == "__main__":
    raise SystemExit(main())
