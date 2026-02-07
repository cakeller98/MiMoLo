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
