# Duplicate Code Opportunities

Detected 4 exact normalized function-body clusters (heuristic).

## Cluster 1
- functions: 3
- avg lines: 16
- candidates:
  - mml.sh:56 :: get_toml_value (16 lines)
  - scripts/bundle_app.sh:48 :: get_toml_value (16 lines)
  - archive/start_scripts/start_control_dev.sh:29 :: get_toml_value (16 lines)

## Cluster 2
- functions: 3
- avg lines: 16
- candidates:
  - mimolo/control_proto/src/control_proto_utils.ts:160 :: deriveStatusLoopMs (16 lines)
  - mimolo/control_proto/src/control_proto_utils.ts:177 :: deriveInstanceLoopMs (16 lines)
  - mimolo/control_proto/src/control_proto_utils.ts:194 :: deriveLogLoopMs (16 lines)

## Cluster 3
- functions: 2
- avg lines: 15
- candidates:
  - tests/test_runtime_widget_ipc_stubs.py:34 :: test_widget_stub_missing_plugin_id (15 lines)
  - tests/test_runtime_widget_ipc_stubs.py:49 :: test_widget_stub_missing_instance_id (15 lines)

## Cluster 4
- functions: 2
- avg lines: 11
- candidates:
  - tests/test_protocol_parse.py:23 :: test_parse_summary (11 lines)
  - tests/test_protocol_parse.py:34 :: test_parse_heartbeat (11 lines)

