# Method And Scope

## Scope
- Languages: Python, TypeScript, Shell
- PowerShell handling: scanned only when not a translated SH pair; parity map always recorded
- Exclusions: node_modules, dist, temp_debug, __pycache__, .venv

## Metrics
- Raw line count per file
- Per-file function stats (min/max/avg lines per function)
- Largest files + longest functions (non-test ranking)

## Static analyses
- Duplicate function-body clusters (exact normalized heuristic)
- Concern-boundary detection via keyword families (non-test focus)
- Python exception handling audit against project policy (non-test focus)
- Path portability and hard-coded timing literal candidate scans

## Known limits
- Function extraction for TS/SH/PS1 is brace-heuristic based (not full parser/AST).
- Duplicate detection is exact-normalized, so semantic near-duplicates may be missed.
- Concern tagging is heuristic and intended for triage, not as a correctness proof.
