[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Mandatory = $true)]
    [string]$Shim,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    return Split-Path -Parent $PSScriptRoot
}

function Get-ShortHelpText {
    return @(
        "MiMoLo short commands",
        "",
        "Commands:",
        "  mimolo --help",
        "  mimolo dash",
        "  mimolo ops --status",
        "  mimolo ops --stop",
        "  mimolo ops --start",
        "  mimolo ops --list-active",
        "  mimolo report [report options]",
        "  mimolo activity [report options]",
        "  mimolo blips [blip options]",
        "  mimolo blips --live --refresh 60",
        "",
        "Shortcuts:",
        "  mimolo-help",
        "  mimolo-dash",
        "  mimolo-ops",
        "  mimolo-report",
        "  mimolo-activity",
        "  mimolo-blips",
        "  mimolo-bliplive",
        "",
        "Notes:",
        "  Python-backed commands prefer the repo .venv and fall back to poetry if needed.",
        "  Before first use on a new profile, verify your security-tool exclusions are present",
        "  for Python, Poetry, pip, pipx, uv, and repo working paths.",
        "",
        "Install links if needed:",
        "  Python 3.11+: https://www.python.org/downloads/",
        "  Poetry:       https://python-poetry.org/docs/#installation"
    )
}

function Show-ShortHelp {
    foreach ($line in Get-ShortHelpText) {
        Write-Output $line
    }
}

function Get-CommandLabel {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return "mimolo"
    }

    return $Value.Trim().ToLowerInvariant()
}

function Invoke-PowerShellScript {
    param(
        [string]$ScriptPath,
        [string[]]$ScriptArgs
    )

    if (-not (Test-Path -LiteralPath $ScriptPath)) {
        throw "Script not found: $ScriptPath"
    }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ScriptPath @ScriptArgs
    exit $LASTEXITCODE
}

function Get-PythonRunner {
    $repoRoot = Get-RepoRoot
    $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) {
        return @{
            Kind = "venv"
            Command = $venvPython
            PrefixArgs = @()
        }
    }

    $poetryCommand = Get-Command poetry -ErrorAction SilentlyContinue
    if ($null -ne $poetryCommand) {
        return @{
            Kind = "poetry"
            Command = $poetryCommand.Source
            PrefixArgs = @("run", "python")
        }
    }

    return $null
}

function Show-PythonDependencyError {
    param([string]$Feature)

    @(
        ("MiMoLo {0} requires the repo Python environment." -f $Feature),
        "Expected:",
        "  - repo .venv\Scripts\python.exe, or",
        "  - Poetry on PATH plus Python 3.11+",
        "",
        "Before first use on a new profile, verify your security-tool exclusions are present",
        "for Python, Poetry, pip, pipx, uv, and repo working paths.",
        "",
        "Install links:",
        "  Python 3.11+: https://www.python.org/downloads/",
        "  Poetry:       https://python-poetry.org/docs/#installation"
    ) | ForEach-Object { Write-Output $_ }

    exit 1
}

function Invoke-PythonModule {
    param(
        [string]$Feature,
        [string]$Module,
        [string[]]$ModuleArgs
    )

    $runner = Get-PythonRunner
    if ($null -eq $runner) {
        Show-PythonDependencyError -Feature $Feature
    }

    & $runner.Command @($runner.PrefixArgs + @("-m", $Module) + $ModuleArgs)
    exit $LASTEXITCODE
}

function Invoke-PythonScript {
    param(
        [string]$Feature,
        [string]$ScriptPath,
        [string[]]$ScriptArgs
    )

    if (-not (Test-Path -LiteralPath $ScriptPath)) {
        throw "Script not found: $ScriptPath"
    }

    $runner = Get-PythonRunner
    if ($null -eq $runner) {
        Show-PythonDependencyError -Feature $Feature
    }

    & $runner.Command @($runner.PrefixArgs + @($ScriptPath) + $ScriptArgs)
    exit $LASTEXITCODE
}

function Invoke-MimoloOps {
    param([string[]]$RawArgs)

    $normalized = @($RawArgs | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($normalized.Count -eq 0) {
        Write-Output "Usage: mimolo ops --status|--stop|--start|--list-active"
        exit 2
    }

    if ($normalized.Count -eq 1 -and ($normalized[0] -eq "--help" -or $normalized[0] -eq "-h")) {
        Write-Output "Usage: mimolo ops --status|--stop|--start|--list-active"
        Write-Output ""
        Write-Output "Options:"
        Write-Output "  --status       Query running Operations over IPC."
        Write-Output "  --stop         Request graceful Operations shutdown over IPC."
        Write-Output "  --start        Launch Operations via mml.ps1 operations."
        Write-Output "  --list-active  Show suspected active MiMoLo processes."
        exit 0
    }

    if ($normalized.Count -ne 1) {
        Write-Output ("Unexpected mimolo ops arguments: {0}" -f ($normalized -join " "))
        Write-Output "Use: mimolo ops --status|--stop|--start|--list-active"
        exit 2
    }

    $repoRoot = Get-RepoRoot
    $launcher = Join-Path $repoRoot "mml.ps1"

    switch -Exact ($normalized[0]) {
        "--status" {
            Invoke-PythonModule -Feature "ops status" -Module "mimolo.cli" -ModuleArgs @("ops-control", "status")
        }
        "--stop" {
            Invoke-PythonModule -Feature "ops stop" -Module "mimolo.cli" -ModuleArgs @("ops-control", "stop")
        }
        "--start" {
            Invoke-PowerShellScript -ScriptPath $launcher -ScriptArgs @("operations")
        }
        "--list-active" {
            Invoke-PowerShellScript -ScriptPath $launcher -ScriptArgs @("list-active")
        }
        default {
            Write-Output ("Bad mimolo ops flag: {0}" -f $normalized[0])
            Write-Output "Use: mimolo ops --status|--stop|--start|--list-active"
            exit 2
        }
    }
}

$repoRoot = Get-RepoRoot
$reportScript = Join-Path $repoRoot "scripts\print_last_jsonl.ps1"
$blipScript = Join-Path $repoRoot "scripts\print_day_blip_chart.py"
$launcherScript = Join-Path $repoRoot "mml.ps1"

$shimName = Get-CommandLabel -Value $Shim
$normalizedArgs = @($Args | Where-Object { $null -ne $_ })

switch -Exact ($shimName) {
    "mimolo" {
        if ($normalizedArgs.Count -eq 0) {
            Show-ShortHelp
            exit 0
        }

        $subcommand = Get-CommandLabel -Value $normalizedArgs[0]
        $subArgs = if ($normalizedArgs.Count -gt 1) { @($normalizedArgs[1..($normalizedArgs.Count - 1)]) } else { @() }

        switch -Exact ($subcommand) {
            "--help" { Show-ShortHelp; exit 0 }
            "-h" { Show-ShortHelp; exit 0 }
            "help" { Show-ShortHelp; exit 0 }
            "dash" { Invoke-PowerShellScript -ScriptPath $launcherScript -ScriptArgs $subArgs }
            "ops" { Invoke-MimoloOps -RawArgs $subArgs }
            "report" { Invoke-PowerShellScript -ScriptPath $reportScript -ScriptArgs $subArgs }
            "activity" { Invoke-PowerShellScript -ScriptPath $reportScript -ScriptArgs (@("--get-last-active") + $subArgs) }
            "blips" { Invoke-PythonScript -Feature "blips" -ScriptPath $blipScript -ScriptArgs $subArgs }
            "bliplive" { Invoke-PythonScript -Feature "bliplive" -ScriptPath $blipScript -ScriptArgs (@("--live", "--refresh", "60") + $subArgs) }
            default {
                Write-Output ("Unknown mimolo command: {0}" -f $normalizedArgs[0])
                Write-Output ""
                Show-ShortHelp
                exit 2
            }
        }
    }
    "mimolo-help" {
        Show-ShortHelp
        exit 0
    }
    "mimolo-dash" {
        Invoke-PowerShellScript -ScriptPath $launcherScript -ScriptArgs $normalizedArgs
    }
    "mimolo-ops" {
        Invoke-MimoloOps -RawArgs $normalizedArgs
    }
    "mimolo-report" {
        Invoke-PowerShellScript -ScriptPath $reportScript -ScriptArgs $normalizedArgs
    }
    "mimolo-activity" {
        Invoke-PowerShellScript -ScriptPath $reportScript -ScriptArgs (@("--get-last-active") + $normalizedArgs)
    }
    "mimolo-blips" {
        Invoke-PythonScript -Feature "blips" -ScriptPath $blipScript -ScriptArgs $normalizedArgs
    }
    "mimolo-bliplive" {
        Invoke-PythonScript -Feature "bliplive" -ScriptPath $blipScript -ScriptArgs (@("--live", "--refresh", "60") + $normalizedArgs)
    }
    default {
        Write-Output ("Unknown MiMoLo shim: {0}" -f $Shim)
        exit 2
    }
}
