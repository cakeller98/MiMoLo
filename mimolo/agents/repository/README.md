# Agent Repository Layout

This folder stores versioned agent zip files.

## Zip naming
<agent_name>_v<version>.zip

Example:
- trail_tracker_v1.2.3.zip

## Zip contents
The zip root must contain a single top-level folder named <agent_name>.

Example zip layout:
<agent_name>/
  manifest.json
  payload_hashes.json
  files/
    <agent_code_files...>

Notes:
- The top-level folder name inside the zip matches the agent name.
- Orchestrator installs by extracting into:
  %AppData%/mimolo/agents/<agent_name>/ (platform equivalents)
- manifest.json is used for metadata and required params.
- payload_hashes.json contains SHA-256 hashes for payload files only.
