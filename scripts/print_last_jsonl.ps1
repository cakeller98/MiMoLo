[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$File,
    [int]$Lines = 20,
    [int]$MaxPaths = 5,
    [switch]$ShowRecentRows,
    [switch]$RawJson,
    [Alias("all")]
    [switch]$IncludeNoops,
    [Alias("h")]
    [switch]$Help,
    [Alias("glh", "gle", "get-last-active", "get-last-heartbeat", "get-last-entry")]
    [switch]$GetLastActive,
    [int]$StaleAfterSeconds = 300,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-HelpText {
    return @(
        "Usage:",
        "  powershell -ExecutionPolicy Bypass -File .\scripts\print_last_jsonl.ps1 [options]",
        "",
        "Options:",
        "  --help, -h                      Show this help text.",
        "  --file <path>                   Read a specific .jsonl file.",
        "  --lines <n>                     Show the last N entries in tail mode. Default: 20.",
        "  --max-paths <n>                 Limit listed paths per entry. Default: 5.",
        "  --show-recent-rows              Include recent_widget_rows in tail mode.",
        "  --raw-json                      Include compact raw JSON data in tail mode.",
        "  --include-noops, --all          Include idle/no-op summaries. Default hides them.",
        "  --get-last-active               Show local time of the most recent meaningful log entry.",
        "  --get-last-heartbeat            Alias for --get-last-active.",
        "  --get-last-entry                Alias for --get-last-active.",
        "  --glh                           Alias for --get-last-active.",
        "  --stale-after-seconds <n>       Freshness threshold for Operations status. Default: 300.",
        "",
        "Examples:",
        "  powershell -ExecutionPolicy Bypass -File .\scripts\print_last_jsonl.ps1",
        "  powershell -ExecutionPolicy Bypass -File .\scripts\print_last_jsonl.ps1 --get-last-active",
        "  powershell -ExecutionPolicy Bypass -File .\scripts\print_last_jsonl.ps1 --include-noops --lines 10",
        "  powershell -ExecutionPolicy Bypass -File .\scripts\print_last_jsonl.ps1 --file .\logs\2026-04-14.mimolo.jsonl --lines 10"
    )
}

function Show-HelpAndExit {
    param(
        [string]$BadArgument,
        [string]$Message,
        [int]$ExitCode = 0
    )

    if (-not [string]::IsNullOrWhiteSpace($BadArgument)) {
        Write-Output ("Bad flag: {0}" -f $BadArgument)
        Write-Output ""
    }
    elseif (-not [string]::IsNullOrWhiteSpace($Message)) {
        Write-Output $Message
        Write-Output ""
    }

    foreach ($line in Get-HelpText) {
        Write-Output $line
    }

    exit $ExitCode
}

function Get-RequiredOptionValue {
    param(
        [string[]]$Tokens,
        [int]$Index,
        [string]$OptionName
    )

    $tokenArray = @($Tokens)
    if (($Index + 1) -ge $tokenArray.Count) {
        Show-HelpAndExit -Message ("Missing value for {0}" -f $OptionName) -ExitCode 2
    }

    $value = $tokenArray[$Index + 1]
    if ([string]::IsNullOrWhiteSpace($value)) {
        Show-HelpAndExit -Message ("Missing value for {0}" -f $OptionName) -ExitCode 2
    }

    return $value
}

function Parse-IntegerOptionValue {
    param(
        [string]$RawValue,
        [string]$OptionName
    )

    $parsed = 0
    if (-not [int]::TryParse($RawValue, [ref]$parsed)) {
        Show-HelpAndExit -Message ("Invalid integer for {0}: {1}" -f $OptionName, $RawValue) -ExitCode 2
    }

    return $parsed
}

function Parse-RawExtraArgs {
    param([string[]]$Tokens)

    $normalizedTokens = @(@($Tokens) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    $unexpected = New-Object System.Collections.Generic.List[string]

    for ($i = 0; $i -lt $normalizedTokens.Count; $i += 1) {
        $token = $normalizedTokens[$i]
        switch -Exact ($token) {
            "--help" {
                $script:Help = $true
                continue
            }
            "--glh" {
                $script:GetLastActive = $true
                continue
            }
            "--gle" {
                $script:GetLastActive = $true
                continue
            }
            "--get-last-active" {
                $script:GetLastActive = $true
                continue
            }
            "--get-last-heartbeat" {
                $script:GetLastActive = $true
                continue
            }
            "--get-last-entry" {
                $script:GetLastActive = $true
                continue
            }
            "--show-recent-rows" {
                $script:ShowRecentRows = $true
                continue
            }
            "--include-noops" {
                $script:IncludeNoops = $true
                continue
            }
            "--all" {
                $script:IncludeNoops = $true
                continue
            }
            "--raw-json" {
                $script:RawJson = $true
                continue
            }
            "--file" {
                $script:File = Get-RequiredOptionValue -Tokens $normalizedTokens -Index $i -OptionName "--file"
                $i += 1
                continue
            }
            "--lines" {
                $rawValue = Get-RequiredOptionValue -Tokens $normalizedTokens -Index $i -OptionName "--lines"
                $script:Lines = Parse-IntegerOptionValue -RawValue $rawValue -OptionName "--lines"
                $i += 1
                continue
            }
            "--max-paths" {
                $rawValue = Get-RequiredOptionValue -Tokens $normalizedTokens -Index $i -OptionName "--max-paths"
                $script:MaxPaths = Parse-IntegerOptionValue -RawValue $rawValue -OptionName "--max-paths"
                $i += 1
                continue
            }
            "--stale-after-seconds" {
                $rawValue = Get-RequiredOptionValue -Tokens $normalizedTokens -Index $i -OptionName "--stale-after-seconds"
                $script:StaleAfterSeconds = Parse-IntegerOptionValue -RawValue $rawValue -OptionName "--stale-after-seconds"
                $i += 1
                continue
            }
            default {
                $unexpected.Add($token)
                continue
            }
        }
    }

    return @($unexpected.ToArray())
}

$unexpectedArgs = @(Parse-RawExtraArgs -Tokens $ExtraArgs)
if ($Help) {
    Show-HelpAndExit -ExitCode 0
}

if ($unexpectedArgs.Count -gt 0) {
    $firstUnexpected = $unexpectedArgs[0]
    if ($firstUnexpected.StartsWith("-")) {
        Show-HelpAndExit -BadArgument $firstUnexpected -ExitCode 2
    }

    Show-HelpAndExit -Message ("Unexpected argument: {0}" -f $firstUnexpected) -ExitCode 2
}

function Get-RepoRoot {
    return Split-Path -Parent $PSScriptRoot
}

function Get-PropertyValue {
    param(
        $Object,
        [string]$Name,
        $Default = $null
    )

    if ($null -eq $Object) {
        return $Default
    }

    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $Default
    }

    return $property.Value
}

function Get-ItemCount {
    param($Value)

    if ($null -eq $Value) {
        return 0
    }

    return @($Value).Count
}

function Format-ByteSize {
    param($Bytes)

    if ($null -eq $Bytes) {
        return $null
    }

    $size = [double]$Bytes
    $units = @("B", "KB", "MB", "GB", "TB")
    $index = 0
    while ($size -ge 1024 -and $index -lt ($units.Count - 1)) {
        $size /= 1024
        $index += 1
    }

    if ($index -eq 0) {
        return ("{0:N0} {1}" -f $size, $units[$index])
    }

    return ("{0:N1} {1}" -f $size, $units[$index])
}

function Format-Timestamp {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return "(no timestamp)"
    }

    try {
        return ([DateTimeOffset]::Parse($Value).ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss zzz"))
    }
    catch {
        return $Value
    }
}

function Format-Duration {
    param($Seconds)

    if ($null -eq $Seconds) {
        return $null
    }

    return ("{0:N1}s" -f [double]$Seconds)
}

function Format-LocalTimeZoneLabel {
    param([System.TimeZoneInfo]$TimeZone)

    $now = [DateTimeOffset]::Now
    $localDateTime = $now.LocalDateTime
    $zoneName = if ($TimeZone.IsDaylightSavingTime($localDateTime)) {
        $TimeZone.DaylightName
    }
    else {
        $TimeZone.StandardName
    }

    if ([string]::IsNullOrWhiteSpace($zoneName)) {
        $zoneName = $TimeZone.Id
    }

    return ("{0} (UTC{1})" -f $zoneName, $now.ToString("zzz"))
}

function Test-IsMeaningfulRecord {
    param($Record)

    $type = Get-PropertyValue $Record "type" "unknown"
    if ($type -ne "event") {
        return $true
    }

    $data = Get-PropertyValue $Record "data"
    $activitySignal = Get-PropertyValue $data "activity_signal"
    $keepAlive = Get-PropertyValue $activitySignal "keep_alive"
    $recordEvent = [string](Get-PropertyValue $data "event" (Get-PropertyValue $Record "event" ""))
    $normalizedEvent = $recordEvent.Trim().ToLowerInvariant()
    $isLifecycleSignal = (
        $normalizedEvent.EndsWith("_session_open") -or
        $normalizedEvent.EndsWith("_session_close") -or
        $normalizedEvent.EndsWith("_open") -or
        $normalizedEvent.EndsWith("_close")
    )

    if ($keepAlive -eq $true -or $isLifecycleSignal) {
        return $true
    }

    if ($keepAlive -eq $false) {
        return $false
    }

    return $true
}

function Get-SelectedRawLines {
    param(
        [string]$Path,
        [int]$Limit,
        [switch]$IncludeNoops
    )

    if ($Limit -le 0) {
        return @()
    }

    if ($IncludeNoops) {
        return @(
            Get-Content -LiteralPath $Path -Tail $Limit -Encoding UTF8 |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
        )
    }

    $matchingLines = New-Object System.Collections.Generic.List[string]
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        $includeLine = $true
        try {
            $record = $line | ConvertFrom-Json
            $includeLine = Test-IsMeaningfulRecord -Record $record
        }
        catch {
            $includeLine = $true
        }

        if ($includeLine) {
            $matchingLines.Add($line)
        }
    }

    return @($matchingLines.ToArray() | Select-Object -Last $Limit)
}

function Format-RelativeAge {
    param([TimeSpan]$Age)

    if ($Age.TotalSeconds -lt 0) {
        $Age = [TimeSpan]::Zero
    }

    if ($Age.TotalHours -ge 1) {
        return ("{0}h {1}m" -f [int]$Age.TotalHours, $Age.Minutes)
    }

    if ($Age.TotalMinutes -ge 1) {
        return ("{0}m {1}s" -f [int]$Age.TotalMinutes, $Age.Seconds)
    }

    return ("{0}s" -f [int][Math]::Round($Age.TotalSeconds))
}

function Format-ExtensionCounts {
    param($Items)

    $parts = @()
    foreach ($item in @($Items)) {
        $ext = Get-PropertyValue $item "ext"
        $count = Get-PropertyValue $item "count"
        if ([string]::IsNullOrWhiteSpace($ext)) {
            continue
        }
        $parts += ("{0} x{1}" -f $ext, $count)
    }

    return ($parts -join ", ")
}

function Format-ChangeLines {
    param(
        [string]$Title,
        $Items,
        [int]$Limit
    )

    $lines = @()
    $count = Get-ItemCount $Items
    if ($count -eq 0) {
        return $lines
    }

    $lines += ("  {0}:" -f $Title)
    $shown = 0
    foreach ($item in @($Items)) {
        if ($shown -ge $Limit) {
            break
        }

        $path = Get-PropertyValue $item "path"
        if ([string]::IsNullOrWhiteSpace($path)) {
            continue
        }

        $ext = Get-PropertyValue $item "ext"
        $sizeText = Format-ByteSize (Get-PropertyValue $item "size")
        $parts = @($path)
        if (-not [string]::IsNullOrWhiteSpace($ext)) {
            $parts += "[{0}]" -f $ext
        }
        if (-not [string]::IsNullOrWhiteSpace($sizeText)) {
            $parts += $sizeText
        }

        $lines += ("    - {0}" -f ($parts -join " | "))
        $shown += 1
    }

    if ($count -gt $shown) {
        $lines += ("    - ... {0} more" -f ($count - $shown))
    }

    return $lines
}

function Format-RecentRows {
    param(
        $Rows,
        [int]$Limit
    )

    $lines = @()
    $count = Get-ItemCount $Rows
    if ($count -eq 0) {
        return $lines
    }

    $lines += "  recent rows:"
    $shown = 0
    foreach ($row in @($Rows)) {
        if ($shown -ge $Limit) {
            break
        }

        $path = Get-PropertyValue $row "path"
        $eventName = Get-PropertyValue $row "event"
        $seenAt = Format-Timestamp (Get-PropertyValue $row "seen_at")
        $sizeText = Format-ByteSize (Get-PropertyValue $row "size")
        $parts = @()
        if (-not [string]::IsNullOrWhiteSpace($eventName)) {
            $parts += $eventName
        }
        if (-not [string]::IsNullOrWhiteSpace($path)) {
            $parts += $path
        }
        if (-not [string]::IsNullOrWhiteSpace($sizeText)) {
            $parts += $sizeText
        }
        $parts += $seenAt
        $lines += ("    - {0}" -f ($parts -join " | "))
        $shown += 1
    }

    if ($count -gt $shown) {
        $lines += ("    - ... {0} more" -f ($count - $shown))
    }

    return $lines
}

function Format-ActivitySignal {
    param($Signal)

    if ($null -eq $Signal) {
        return $null
    }

    $mode = Get-PropertyValue $Signal "mode"
    $keepAlive = Get-PropertyValue $Signal "keep_alive"
    $reason = Get-PropertyValue $Signal "reason"

    $parts = @()
    if (-not [string]::IsNullOrWhiteSpace($mode)) {
        $parts += ("mode={0}" -f $mode)
    }
    if ($null -ne $keepAlive) {
        $parts += ("keep_alive={0}" -f $keepAlive.ToString().ToLowerInvariant())
    }
    if (-not [string]::IsNullOrWhiteSpace($reason)) {
        $parts += $reason
    }

    if ($parts.Count -eq 0) {
        return $null
    }

    return ($parts -join " | ")
}

function Format-CompactJson {
    param($Object)

    if ($null -eq $Object) {
        return $null
    }

    $json = $Object | ConvertTo-Json -Depth 20 -Compress
    if ($json.Length -le 220) {
        return $json
    }

    return ($json.Substring(0, 217) + "...")
}

function Format-Record {
    param(
        $Record,
        [int]$Index,
        [switch]$IncludeRecentRows,
        [switch]$ShowRawRecord,
        [int]$PathLimit
    )

    $lines = @()
    $type = Get-PropertyValue $Record "type" "unknown"

    if ($type -eq "event") {
        $timestamp = Format-Timestamp (Get-PropertyValue $Record "timestamp")
        $label = Get-PropertyValue $Record "label" "(no label)"
        $eventName = Get-PropertyValue $Record "event" "(no event)"
        $data = Get-PropertyValue $Record "data"

        $lines += ("[{0}] EVENT   {1} | {2} | {3}" -f $Index, $timestamp, $label, $eventName)

        $schema = Get-PropertyValue $data "schema"
        if (-not [string]::IsNullOrWhiteSpace($schema)) {
            $lines += ("  schema: {0}" -f $schema)
        }

        $watchPaths = @()
        foreach ($watchPath in @(Get-PropertyValue $data "watch_paths")) {
            if (-not [string]::IsNullOrWhiteSpace($watchPath)) {
                $watchPaths += $watchPath
            }
        }
        if ($watchPaths.Count -gt 0) {
            $lines += ("  watch: {0}" -f ($watchPaths -join " ; "))
        }

        $window = Get-PropertyValue $data "window"
        if ($null -ne $window) {
            $start = Format-Timestamp (Get-PropertyValue $window "start")
            $end = Format-Timestamp (Get-PropertyValue $window "end")
            $duration = Format-Duration (Get-PropertyValue $window "duration_s")
            $lines += ("  window: {0} -> {1} ({2})" -f $start, $end, $duration)
        }

        $counts = Get-PropertyValue $data "counts"
        if ($null -ne $counts) {
            $lines += (
                "  counts: total={0} created={1} modified={2} deleted={3} renamed={4}" -f
                (Get-PropertyValue $counts "total" 0),
                (Get-PropertyValue $counts "created" 0),
                (Get-PropertyValue $counts "modified" 0),
                (Get-PropertyValue $counts "deleted" 0),
                (Get-PropertyValue $counts "renamed" 0)
            )
        }

        $signalText = Format-ActivitySignal (Get-PropertyValue $data "activity_signal")
        if (-not [string]::IsNullOrWhiteSpace($signalText)) {
            $lines += ("  activity: {0}" -f $signalText)
        }

        $backend = Get-PropertyValue $data "backend"
        if (-not [string]::IsNullOrWhiteSpace($backend)) {
            $lines += ("  backend: {0}" -f $backend)
        }

        $topExtensions = Format-ExtensionCounts (Get-PropertyValue $data "top_extensions")
        if (-not [string]::IsNullOrWhiteSpace($topExtensions)) {
            $lines += ("  top extensions: {0}" -f $topExtensions)
        }

        $lines += Format-ChangeLines -Title "created" -Items (Get-PropertyValue $data "created_paths") -Limit $PathLimit
        $lines += Format-ChangeLines -Title "modified" -Items (Get-PropertyValue $data "modified_paths") -Limit $PathLimit
        $lines += Format-ChangeLines -Title "deleted" -Items (Get-PropertyValue $data "deleted_paths") -Limit $PathLimit

        $pathSamples = @()
        foreach ($sample in @(Get-PropertyValue $data "path_samples")) {
            if (-not [string]::IsNullOrWhiteSpace($sample)) {
                $pathSamples += $sample
            }
        }
        if ($pathSamples.Count -gt 0) {
            $lines += "  samples:"
            foreach ($sample in $pathSamples | Select-Object -First $PathLimit) {
                $lines += ("    - {0}" -f $sample)
            }
            if ($pathSamples.Count -gt $PathLimit) {
                $lines += ("    - ... {0} more" -f ($pathSamples.Count - $PathLimit))
            }
        }

        $trailDir = Get-PropertyValue $data "trail_dir"
        if (-not [string]::IsNullOrWhiteSpace($trailDir)) {
            $lines += ("  trail dir: {0}" -f $trailDir)
        }

        $sessionId = Get-PropertyValue $data "session_id"
        if (-not [string]::IsNullOrWhiteSpace($sessionId)) {
            $lines += ("  session: {0}" -f $sessionId)
        }

        $sessionStarted = Get-PropertyValue $data "session_started_at"
        if (-not [string]::IsNullOrWhiteSpace($sessionStarted)) {
            $lines += ("  session started: {0}" -f (Format-Timestamp $sessionStarted))
        }

        $lastActivity = Get-PropertyValue $data "last_activity_at"
        if (-not [string]::IsNullOrWhiteSpace($lastActivity)) {
            $lines += ("  last activity: {0}" -f (Format-Timestamp $lastActivity))
        }

        $fileInfo = Get-PropertyValue $data "file"
        if ($null -ne $fileInfo) {
            $fileName = Get-PropertyValue $fileInfo "name"
            $fileSize = Format-ByteSize (Get-PropertyValue $fileInfo "size_bytes")
            $sizeDelta = Get-PropertyValue $fileInfo "size_delta_bytes"
            $sizeDeltaText = $null
            if ($null -ne $sizeDelta) {
                $sizeDeltaText = ("delta={0}" -f (Format-ByteSize $sizeDelta))
            }
            $modifiedAt = Format-Timestamp (Get-PropertyValue $fileInfo "modified_at")

            $parts = @()
            if (-not [string]::IsNullOrWhiteSpace($fileName)) {
                $parts += $fileName
            }
            if (-not [string]::IsNullOrWhiteSpace($fileSize)) {
                $parts += $fileSize
            }
            if (-not [string]::IsNullOrWhiteSpace($sizeDeltaText)) {
                $parts += $sizeDeltaText
            }
            if (-not [string]::IsNullOrWhiteSpace($modifiedAt)) {
                $parts += ("modified {0}" -f $modifiedAt)
            }
            if ($parts.Count -gt 0) {
                $lines += ("  file: {0}" -f ($parts -join " | "))
            }
        }

        if ($IncludeRecentRows) {
            $lines += Format-RecentRows -Rows (Get-PropertyValue $data "recent_widget_rows") -Limit $PathLimit
        }

        if ($ShowRawRecord) {
            $rawData = Format-CompactJson $data
            if (-not [string]::IsNullOrWhiteSpace($rawData)) {
                $lines += ("  raw data: {0}" -f $rawData)
            }
        }

        return ($lines -join [Environment]::NewLine)
    }

    if ($type -eq "segment") {
        $start = Format-Timestamp (Get-PropertyValue $Record "start")
        $end = Format-Timestamp (Get-PropertyValue $Record "end")
        $duration = Format-Duration (Get-PropertyValue $Record "duration_s")
        $lines += ("[{0}] SEGMENT {1} -> {2} ({3})" -f $Index, $start, $end, $duration)

        $labels = @()
        foreach ($label in @(Get-PropertyValue $Record "labels")) {
            if (-not [string]::IsNullOrWhiteSpace($label)) {
                $labels += $label
            }
        }
        if ($labels.Count -gt 0) {
            $lines += ("  labels: {0}" -f ($labels -join ", "))
        }

        $resetsCount = Get-PropertyValue $Record "resets_count"
        if ($null -ne $resetsCount) {
            $lines += ("  resets: {0}" -f $resetsCount)
        }

        $events = Get-PropertyValue $Record "events"
        $eventCount = Get-ItemCount $events
        if ($eventCount -gt 0) {
            $lines += ("  linked events: {0}" -f $eventCount)
        }

        $aggregated = Get-PropertyValue $Record "aggregated"
        if ($null -ne $aggregated) {
            $lines += ("  aggregated: {0}" -f (Format-CompactJson $aggregated))
        }

        return ($lines -join [Environment]::NewLine)
    }

    $json = Format-CompactJson $Record
    return ("[{0}] {1}" -f $Index, $json)
}

function Resolve-LogFile {
    param([string]$RequestedPath)

    if (-not [string]::IsNullOrWhiteSpace($RequestedPath)) {
        $resolved = Resolve-Path -LiteralPath $RequestedPath -ErrorAction Stop
        return $resolved.Path
    }

    $logDir = Join-Path (Get-RepoRoot) "logs"
    $candidate = Get-ChildItem -Path $logDir -Filter "*.mimolo.jsonl" -File |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if ($null -eq $candidate) {
        throw "No MiMoLo JSONL log files found in $logDir"
    }

    return $candidate.FullName
}

function Get-LastNonEmptyLine {
    param([string]$Path)

    $candidates = @(Get-Content -LiteralPath $Path -Tail 50 -Encoding UTF8)
    for ($i = $candidates.Count - 1; $i -ge 0; $i -= 1) {
        $line = $candidates[$i]
        if (-not [string]::IsNullOrWhiteSpace($line)) {
            return $line
        }
    }

    return $null
}

function Get-RecordTimestampValue {
    param($Record)

    $timestamp = Get-PropertyValue $Record "timestamp"
    if (-not [string]::IsNullOrWhiteSpace($timestamp)) {
        return $timestamp
    }

    $end = Get-PropertyValue $Record "end"
    if (-not [string]::IsNullOrWhiteSpace($end)) {
        return $end
    }

    $start = Get-PropertyValue $Record "start"
    if (-not [string]::IsNullOrWhiteSpace($start)) {
        return $start
    }

    return $null
}

function Show-LastEntrySummary {
    param(
        [string]$Path,
        [System.TimeZoneInfo]$TimeZone,
        [int]$StaleSeconds,
        [switch]$IncludeNoops
    )

    $rawLines = Get-SelectedRawLines -Path $Path -Limit 1 -IncludeNoops:$IncludeNoops
    $rawLine = if (@($rawLines).Count -gt 0) { @($rawLines)[0] } else { $null }
    if ([string]::IsNullOrWhiteSpace($rawLine)) {
        Write-Output ("File: {0}" -f $Path)
        Write-Output ("Timezone: {0} (local)" -f (Format-LocalTimeZoneLabel -TimeZone $TimeZone))
        Write-Output ("Filter: {0}" -f $(if ($IncludeNoops) { "including no-ops" } else { "meaningful only" }))
        if ($IncludeNoops) {
            Write-Output "No lines found."
        } else {
            Write-Output "No meaningful entries matched the default filter. Use --include-noops to include idle summaries."
        }
        return
    }

    $entryTimestamp = $null
    $entryType = "unknown"
    $entryLabel = $null
    $entryEvent = $null

    try {
        $record = $rawLine | ConvertFrom-Json
        $timestampValue = Get-RecordTimestampValue -Record $record
        if (-not [string]::IsNullOrWhiteSpace($timestampValue)) {
            $entryTimestamp = [DateTimeOffset]::Parse($timestampValue)
        }
        $entryType = Get-PropertyValue $record "type" "unknown"
        $entryLabel = Get-PropertyValue $record "label"
        $entryEvent = Get-PropertyValue $record "event"
    }
    catch {
        $entryTimestamp = $null
    }

    if ($null -eq $entryTimestamp) {
        $fileInfo = Get-Item -LiteralPath $Path
        $entryTimestamp = [DateTimeOffset]$fileInfo.LastWriteTime
    }

    $localTimestamp = $entryTimestamp.ToLocalTime()
    $age = [DateTimeOffset]::Now - $localTimestamp
    if ($age.TotalSeconds -lt 0) {
        $age = [TimeSpan]::Zero
    }

    $opsState = if ($age.TotalSeconds -le $StaleSeconds) { "up" } else { "stale/down" }

    Write-Output ("File: {0}" -f $Path)
    Write-Output ("Timezone: {0} (local)" -f (Format-LocalTimeZoneLabel -TimeZone $TimeZone))
    Write-Output ("Filter: {0}" -f $(if ($IncludeNoops) { "including no-ops" } else { "meaningful only" }))
    Write-Output ("Last entry: {0}" -f $localTimestamp.ToString("yyyy-MM-dd HH:mm:ss zzz"))
    Write-Output ("Age: {0}" -f (Format-RelativeAge -Age $age))
    Write-Output ("Operations: {0} (fresh threshold: {1}s)" -f $opsState, $StaleSeconds)

    $parts = @()
    if (-not [string]::IsNullOrWhiteSpace($entryType)) {
        $parts += $entryType
    }
    if (-not [string]::IsNullOrWhiteSpace($entryLabel)) {
        $parts += $entryLabel
    }
    if (-not [string]::IsNullOrWhiteSpace($entryEvent)) {
        $parts += $entryEvent
    }
    if ($parts.Count -gt 0) {
        Write-Output ("Source: {0}" -f ($parts -join " | "))
    }
}

$localTimeZone = [System.TimeZoneInfo]::Local
$targetFile = Resolve-LogFile -RequestedPath $File

if ($GetLastActive) {
    Show-LastEntrySummary -Path $targetFile -TimeZone $localTimeZone -StaleSeconds $StaleAfterSeconds -IncludeNoops:$IncludeNoops
    exit 0
}

$rawLines = @(Get-SelectedRawLines -Path $targetFile -Limit $Lines -IncludeNoops:$IncludeNoops)

if ($rawLines.Count -eq 0) {
    Write-Output ("File: {0}" -f $targetFile)
    Write-Output ("Timezone: {0} (local)" -f (Format-LocalTimeZoneLabel -TimeZone $localTimeZone))
    Write-Output ("Filter: {0}" -f $(if ($IncludeNoops) { "including no-ops" } else { "meaningful only" }))
    if ($IncludeNoops) {
        Write-Output "No lines found."
    } else {
        Write-Output "No meaningful entries matched the default filter. Use --include-noops to include idle summaries."
    }
    exit 0
}

Write-Output ("File: {0}" -f $targetFile)
Write-Output ("Timezone: {0} (local)" -f (Format-LocalTimeZoneLabel -TimeZone $localTimeZone))
Write-Output ("Filter: {0}" -f $(if ($IncludeNoops) { "including no-ops" } else { "meaningful only" }))
$entryDescriptor = if ($IncludeNoops) { "entries" } elseif ($rawLines.Count -eq 1) { "meaningful entry" } else { "meaningful entries" }
Write-Output ("Showing last {0} {1}" -f $rawLines.Count, $entryDescriptor)
Write-Output ""

$displayIndex = 1
foreach ($rawLine in $rawLines) {
    if ([string]::IsNullOrWhiteSpace($rawLine)) {
        continue
    }

    try {
        $record = $rawLine | ConvertFrom-Json
        $rendered = Format-Record -Record $record -Index $displayIndex -IncludeRecentRows:$ShowRecentRows -ShowRawRecord:$RawJson -PathLimit $MaxPaths
    }
    catch {
        $rendered = ("[{0}] RAW     {1}" -f $displayIndex, $rawLine)
    }

    Write-Output $rendered
    Write-Output ""
    $displayIndex += 1
}
