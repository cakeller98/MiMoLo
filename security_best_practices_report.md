# Security Best Practices Report

## Executive Summary
This review focused on the Python core and the TypeScript/Electron components in the repository. The main security gap is a command-injection risk in the debug tail window helper when log paths are interpolated into shell commands. There are also secure-by-default gaps in the Electron main process configuration and log file permissions. No critical vulnerabilities were identified.

## High Severity

### H-01: Shell command injection via log path interpolation in debug tail windows
**Location:** `mimolo/core/agent_debug.py:45-59`

**Description:** The debug tail helper builds shell commands with a raw `stderr_log_path` string for Linux (`xterm -e`, `gnome-terminal -- bash -c`, and `sh -c`). If the log path contains shell metacharacters, a crafted value could execute arbitrary commands under the current user context.

**Why it matters:** If an attacker can influence the log path (e.g., via a config-controlled agent label used in the log filename), this becomes a local code execution vector when debug windows are opened.

**Recommendation:** Avoid shell interpretation and pass arguments as a list wherever possible. For terminal emulators that require `-c`, wrap the path using a safe escaping method (e.g., `shlex.quote`) or switch to a terminal option that accepts argument vectors. Also sanitize/normalize `stderr_log_path` to a safe filename subset.

## Medium Severity

### M-01: Electron BrowserWindow lacks explicit secure-by-default settings
**Location:** `mimolo-control/src/main.ts:4-10`

**Description:** The Electron `BrowserWindow` is created without explicitly setting `webPreferences`. While some defaults are safer in modern Electron, best practice is to enforce `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`, and `enableRemoteModule: false` explicitly to prevent regressions or default changes from weakening security.

**Recommendation:** Set `webPreferences` explicitly for defense in depth. If you later load remote content, also enforce a strict Content Security Policy and `allowRunningInsecureContent: false`.

### M-02: Log files rely on default umask for permissions
**Location:** `mimolo/core/sink.py:104-105`, `mimolo/core/sink.py:197-198`

**Description:** Log files are opened with the default permissions inherited from the system umask. On systems with a permissive umask, logs can become world-readable. The log directory is created with `0o700`, but existing directories or parent permissions can still expose files.

**Recommendation:** Create log files with an explicit `0o600` mode (owner read/write) via `os.open(..., 0o600)` and pass an `opener=` to `open()`, or set a strict umask for the process when opening log files.

## Low Severity

### L-01: Config-driven executable paths are not constrained
**Location:** `mimolo/core/agent_process.py:182-235`

**Description:** The agent subprocess executable and args are taken directly from config. This is likely by design, but it means any party who can modify the config can execute arbitrary binaries under the orchestrator's user.

**Recommendation:** Treat the config file as a privileged input and ensure it is stored with restrictive permissions. If you want stricter defaults, consider an allowlist of executable paths or signed agent manifests.
