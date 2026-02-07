# Control IPC Prototype (TypeScript)

This is a lightweight IPC test harness (no Electron yet). It connects to the orchestrator over AF_UNIX sockets and sends a simple command.

## Setup

```bash
cd mimolo/control_proto
npm install
```

## Run

```bash
MIMOLO_IPC_PATH=... npm run build
MIMOLO_IPC_PATH=... npm run start
```

## Notes
- This is a temporary prototype to validate IPC wiring.
- The message contract will align with the orchestrator IPC API once implemented.
