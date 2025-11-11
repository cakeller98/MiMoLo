from typer.testing import CliRunner

from mimolo.cli import app


def test_cli_test_command_outputs_expected_lines() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["test", "--rate", "1000", "--count", "3"])
    assert result.exit_code == 0
    # Should contain exactly 3 event lines (JSON lines printed via print())
    lines = [ln for ln in result.output.splitlines() if ln.startswith("{") and ln.endswith("}")]
    assert len(lines) == 3


def test_cli_monitor_dry_run(tmp_path) -> None:
    # Use a temp config file that exists but empty -> load_config should fail,
    # so prefer passing no file and rely on default via --dry-run
    runner = CliRunner()
    result = runner.invoke(app, ["monitor", "--dry-run"])
    # Dry-run should not error
    assert result.exit_code == 0
    assert "Dry-run mode" in result.output
