# MiMoLo Terminology Map (Deprecated → Current)

This document maps legacy naming to the current vocabulary. It preserves history
while keeping the docs consistent going forward. The goal is to keep migration
context until transitions are complete; once a rename is fully done and no longer
needs explanation, we can remove it.

## Core Roles
- **Agent** → **Agent**
- **Reporter/Exporter** → **Reporter**
<<<<<<< Updated upstream
- **Dashboard** → **Control** (rename in progress; keep until docs/code/UI fully updated)
- **Orchestrator** → **Operations** (rename in progress; keep until docs/code/UI fully updated)

## Core Responsibilities
- **Agents are plugins** that perform monitoring and provide source data to Operations.
- **Operations manages the Vault of data** and orchestrates agent lifecycles.
- **Control (Dashboard)** is the user interface to Operations (the backend).
- **Reporters are plugins** in Control that transform information into human-readable formats.
- **Archivists (future, maybe)** are Operations-side plugins for backup, encryption, or remote
  forwarding. For now, Operations handles these duties directly.

## Plugin Installation Model
- All plugin types are installed through Control.
- Agents are installed into the Agents area and communicate with Operations.
- Reporters are installed into the Reporters area and primarily communicate with Control.
- Archivists (if introduced) would be installed into Operations and communicate with Operations.

## Notes
=======
<<<<<<< HEAD
- **Vault manager plugin** → **Archivist** (use “Vault Archivist” when disambiguation helps)
- **Dashboard** → **Control** (future rename; not implemented yet)
- **Orchestrator** → **Operations** (future rename; not implemented yet)

## Notes
- **Code identifiers** remain unchanged for now (e.g., `field_agent` in config).
- **Docs/UI** should use the current terms above, and mention deprecated terms
  once when introducing a concept.
- **Archiver naming:** use **Zipper** for compression utilities to avoid confusion
  with Archivist.
- **Why one-word roles:** class/identifier names stack quickly; one-word roles keep
  names concise and readable as systems compose.

=======
- **Dashboard** → **Control** (rename in progress; keep until docs/code/UI fully updated)
- **Orchestrator** → **Operations** (rename in progress; keep until docs/code/UI fully updated)

## Core Responsibilities
- **Agents are plugins** that perform monitoring and provide source data to Operations.
- **Operations manages the Vault of data** and orchestrates agent lifecycles.
- **Control (Dashboard)** is the user interface to Operations (the backend).
- **Reporters are plugins** in Control that transform information into human-readable formats.
- **Archivists (future, maybe)** are Operations-side plugins for backup, encryption, or remote
  forwarding. For now, Operations handles these duties directly.

## Plugin Installation Model
- All plugin types are installed through Control.
- Agents are installed into the Agents area and communicate with Operations.
- Reporters are installed into the Reporters area and primarily communicate with Control.
- Archivists (if introduced) would be installed into Operations and communicate with Operations.

## Notes
>>>>>>> Stashed changes
- **Legacy plugins** refer only to the deprecated in-process, one-way monitor model.
- **Code identifiers** use current terms (e.g., `agent` in config).
- **Docs/UI** should use current terms and mention deprecated terms once when introducing a concept.
- Remove entries from this map only when the transition is complete and no longer
  needs explanation.
<<<<<<< Updated upstream
=======
>>>>>>> b233aa1140cf7e8a3cd96e606985c6300d31b1d7
>>>>>>> Stashed changes
