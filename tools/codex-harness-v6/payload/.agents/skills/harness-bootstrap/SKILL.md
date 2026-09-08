---
name: harness-bootstrap
description: Initialize or refresh the harness only when commands/layout are uninitialized or the environment/project structure materially changed. Do not run as routine per-task setup.
---
# Harness Bootstrap — bounded refresh

Use this Skill only for initial installation, uninitialized verification commands, or a material environment/layout/toolchain change.

1. Do not modify product behavior.
2. Run `detect_project.py` and inspect only the manifests/config/CI/entry points needed to confirm the actual layout and commands.
3. Do not reread all tests, docs, source, or legacy code just to refresh Harness metadata.
4. Update existing `docs/project.md`, `docs/environment.md`, `docs/architecture.md`, `docs/commands.md`, `docs/conventions.md` only when their verified facts changed; do not rewrite unchanged docs.
5. Register only confirmed safe commands in `commands.json`.
6. Run `doctor.py` once after Harness/environment changes; v6 doctor delegates to Self Test. Normal feature work must not invoke bootstrap/doctor routinely.
7. Do not add dependencies solely to make bootstrap succeed.
