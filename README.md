# MiMoLo
MiMoLo (Mini Modular Monitor &amp; Logger) is a lightweight, plugin-based event tracker that records and aggregates workflow activity into clear, time-based segments. It’s modular, extensible, and console-friendly: turning raw events into human-readable logs without invasive tracking or complexity.

Quick log tail helper:
`powershell -ExecutionPolicy Bypass -File .\scripts\print_last_jsonl.ps1`

Quick last-entry check:
`powershell -ExecutionPolicy Bypass -File .\scripts\print_last_jsonl.ps1 --get-last-active`

Help:
`powershell -ExecutionPolicy Bypass -File .\scripts\print_last_jsonl.ps1 --help`

Quick day blip chart:
`poetry run python .\scripts\print_day_blip_chart.py`

Install per-user wrapper in `%LOCALAPPDATA%\bin`:
`cmd /c .\scripts\install_mimolo_short_commands.bat`

Short commands after install:
`mimolo --help`
