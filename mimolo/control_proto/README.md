# Control IPC Prototype (Electron + TypeScript)

This is the active Control prototype testbed. It opens an Electron window,
pings Operations over AF_UNIX IPC, and streams Operations output from a
launcher-managed log file.

## Setup

```bash
cd mimolo/control_proto
npm install
```

## Build

```bash
MIMOLO_IPC_PATH=... npm run build
```

## Run (Electron prototype)

```bash
MIMOLO_IPC_PATH=... MIMOLO_OPS_LOG_PATH=... npm run start
```

## CLI Harness (legacy)

The original one-shot socket client is still available:

```bash
MIMOLO_IPC_PATH=... npm run start:cli
```

## Recommended Launch

From repo root, use the canonical launcher:

```bash
./mml.sh
```

To explicitly refresh portable runtime artifacts:

```bash
./mml.sh prepare
```

Default portable deploy seeds all agent ids listed in the active source list:

- `mimolo/agents/sources.json` by default
- override with `release_agents_path` in `mml.toml` (or `MIMOLO_RELEASE_AGENTS_PATH`)

## Portable-Test Defaults

`mml.sh` runs in portable-test mode by default and sets:

- `MIMOLO_DATA_DIR`
- `MIMOLO_BIN_DIR`
- `MIMOLO_RUNTIME_CONFIG_PATH`
- `MIMOLO_IPC_PATH`
- `MIMOLO_OPS_LOG_PATH`
- `MIMOLO_MONITOR_LOG_DIR`
- `MIMOLO_MONITOR_JOURNAL_DIR`
- `MIMOLO_MONITOR_CACHE_DIR`

All runtime writes are directed to `./temp_debug/...` unless overridden in
`mml.toml` or via environment variables.
