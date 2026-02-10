# Process inspection helpers for mml launcher.

list_mimolo_processes() {
  if ! command -v ps >/dev/null 2>&1; then
    echo "[dev-stack] ps command not available on PATH."
    return 1
  fi

  local pattern="$SCRIPT_DIR|mimolo\\.cli (ops|monitor)|mimolo-control|control_proto|mml\\.(sh|ps1)|MiMoLo"
  echo "[dev-stack] MiMoLo-related processes:"
  local ps_output=""
  if ! ps_output="$(ps -axo pid,ppid,stat,etime,command 2>/dev/null)"; then
    echo "[dev-stack] unable to query process table (permission denied or unsupported environment)."
    return 0
  fi
  if command -v rg >/dev/null 2>&1; then
    printf "%s\n" "$ps_output" | rg -N -i "$pattern" || true
  else
    printf "%s\n" "$ps_output" | grep -Ei "$pattern" || true
  fi
}
