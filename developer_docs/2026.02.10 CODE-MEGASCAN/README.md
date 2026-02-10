# 2026-02-10 Code Megascan

This folder contains a repository-wide static audit for maintainability and policy-smell triage.

Primary entry points:
- `00_METHOD_AND_SCOPE.md`
- `06_EXEC_SUMMARY.md`
- `05_RISK_REGISTER_AND_REFACTOR_QUEUE.md`

Artifacts:
- `01_FILE_METRICS.csv`
- `01A_PS1_PARITY_MAP.csv`
- `02_DUPLICATION_REPORT.md`
- `02A_PY_EXCEPTION_AUDIT.csv`
- `03_CONCERN_BOUNDARY_REPORT.md`
- `03_MIXED_CONCERNS.csv`
- `04_PY_EXCEPTION_AUDIT.md`
- `04_PATH_PORTABILITY_CANDIDATES.csv`
- `05_TIMING_LITERAL_CANDIDATES.csv`
- `06_API_SURFACE_INDEX.csv`

Policy notes:
- PS1 files that are translated SH counterparts are documented in parity mapping and skipped from full redundant scoring.
- Exception audit findings are non-test files only and aligned to project try/except policy.
- Concern and duplication analyses are heuristic triage signals, not compiler/AST proofs.
