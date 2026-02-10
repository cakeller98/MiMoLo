# Risk Register And Refactor Queue

## Priority framing
1. Exception-handling violations (correctness/safety)
2. Large mixed-concern orchestration files (maintainability)
3. Duplicate logic clusters (drift risk)
4. Path portability + timing-literal policy consistency

## Immediate candidates
- mimolo/control_proto/src/ui_html.ts
  - size: 2128
  - concerns: ui_render|ipc_transport|config_policy|filesystem_io|plugin_packaging|polling_timing|logging_diag|cli_scripts|security_trust
- mimolo/utils/src/pack-agent.ts
  - size: 1030
  - concerns: config_policy|filesystem_io|plugin_packaging|logging_diag|cli_scripts
- mimolo/core/runtime.py
  - size: 944
  - concerns: ui_render|ipc_transport|process_lifecycle|config_policy|filesystem_io|plugin_packaging|polling_timing|logging_diag|cli_scripts|security_trust
- mimolo/control_proto/src/main.ts
  - size: 840
  - concerns: ui_render|ipc_transport|config_policy|filesystem_io|plugin_packaging|polling_timing|logging_diag|cli_scripts|security_trust
- mml.sh
  - size: 681
  - concerns: ui_render|ipc_transport|config_policy|filesystem_io|plugin_packaging|polling_timing|logging_diag|cli_scripts|security_trust
- mimolo/agents/screen_tracker/screen_tracker.py
  - size: 655
  - concerns: process_lifecycle|config_policy|filesystem_io|plugin_packaging|polling_timing|logging_diag|cli_scripts
- mimolo/core/runtime_ipc_commands.py
  - size: 618
  - concerns: ui_render|ipc_transport|config_policy|filesystem_io|plugin_packaging|logging_diag
- mimolo/control_proto/src/control_operations.ts
  - size: 446
  - concerns: ipc_transport|process_lifecycle|config_policy|filesystem_io|polling_timing|logging_diag|cli_scripts
- mimolo/core/sink.py
  - size: 431
  - concerns: ui_render|config_policy|filesystem_io|logging_diag|security_trust
- mimolo/agents/client_folder_activity/client_folder_activity.py
  - size: 394
  - concerns: config_policy|filesystem_io|polling_timing|logging_diag|cli_scripts
- mimolo/core/plugin_store.py
  - size: 394
  - concerns: ui_render|config_policy|filesystem_io|plugin_packaging|logging_diag|security_trust
- scripts/bundle_app.sh
  - size: 378
  - concerns: ui_render|ipc_transport|config_policy|filesystem_io|plugin_packaging|logging_diag|cli_scripts
- mimolo/core/agent_process.py
  - size: 373
  - concerns: ipc_transport|process_lifecycle|config_policy|filesystem_io|plugin_packaging|polling_timing|logging_diag|security_trust
- mimolo/core/runtime_shutdown.py
  - size: 340
  - concerns: ipc_transport|config_policy|polling_timing|logging_diag
- mimolo/control_proto/src/control_persistent_ipc.ts
  - size: 339
  - concerns: ipc_transport|polling_timing|logging_diag|cli_scripts

## Exception policy findings
- total findings (non-test): 134
- details: see 02A_PY_EXCEPTION_AUDIT.csv and 04_PY_EXCEPTION_AUDIT.md
