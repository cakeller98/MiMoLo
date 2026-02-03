# Security Agent Guide

## Purpose
This document defines ongoing security best practices for MiMoLo. It is meant for maintainers and contributors to keep security guarantees consistent as the codebase evolves.

## Scope
This guide applies to:
- Python core runtime and CLI
- TypeScript/Electron dashboard
- Configuration, logging, and IPC

## Security Goals
- Prevent command injection and unsafe process spawning
- Preserve data confidentiality in logs and configs
- Enforce secure defaults in Electron
- Keep IPC access constrained to the local user

## Secure-by-Default Rules
- Do not build shell commands using untrusted strings. Prefer argument arrays.
- If a shell is unavoidable, escape inputs with `shlex.quote` and document why.
- Prefer explicit security settings over framework defaults.
- Create sensitive files with explicit restrictive permissions.
- Treat configuration files as privileged inputs.

## Python Core Guidelines
- Subprocesses must use list arguments, not string commands.
- Avoid `shell=True`. Only allow it with a documented exception.
- When writing log files, use owner-only permissions.
- Ensure socket files are created with restrictive permissions.

## Electron Guidelines
- Always set `webPreferences` explicitly.
- Require `contextIsolation: true`.
- Require `nodeIntegration: false`.
- Require `sandbox: true`.
- Require `enableRemoteModule: false`.
- Avoid loading remote URLs in production.
- If remote content is required, enforce a strict CSP.

## Configuration Security
- Store config files with owner-only permissions where possible.
- If the config controls executable paths, treat config updates as privileged.
- Document any allowlists or signatures if introduced.

## Logging and Data Handling
- Log directory should be `0700`.
- Log files should be `0600`.
- Never log secrets, access tokens, or raw credentials.

## IPC Security
- Use Unix domain sockets with restrictive permissions.
- Validate socket paths to avoid path traversal or oversized paths.
- Do not accept IPC messages from non-local origins.

## Code Review Checklist
- Any subprocess call is argument-list based.
- Any file write for logs or config uses explicit permissions.
- Electron window creation enforces secure `webPreferences`.
- New config options do not expand attack surface without justification.
- New dependencies have a clear purpose and are kept minimal.

## Testing Requirements
- Add tests for shell-escape or non-shell subprocess logic.
- Add tests that verify log file permissions on supported platforms.
- Add a smoke test for Electron window configuration settings.

## Ongoing Maintenance
- Re-run security review on any change that touches subprocess execution.
- Re-run security review on any change that touches config loading or file paths.
- Re-run security review on any change that touches logging output.
- Re-run security review on any change that touches IPC mechanisms.
- Re-run security review on any change that touches Electron window creation.

## Exceptions
- Any deviation from these rules must be documented in the PR and in this file.
