<#
    Daily news podcast — unattended pipeline.

    fetch feeds -> curate (headless Claude) -> render speech -> deliver to OneDrive

    Runs from Task Scheduler on weekday mornings. Everything is logged, because
    a job that fails silently at 8:47am is worse than no job at all.
#>
[CmdletBinding()]
param(
    [switch]$SkipCurate,   # re-render an existing script.md without re-curating
    [switch]$NoDeliver     # build only, don't copy to OneDrive
)

$ErrorActionPreference = 'Stop'

$Proj    = 'C:\Users\gurpr\news-podcast'
$Python  = 'C:\Users\gurpr\AppData\Local\Microsoft\WindowsApps\python.exe'
$Claude  = 'C:\Users\gurpr\.local\bin\claude.exe'
$Deliver = 'C:\Users\gurpr\OneDrive\News Podcast'

$Date    = Get-Date -Format 'yyyy-MM-dd'
$LogDir  = Join-Path $Proj 'logs'
$LogFile = Join-Path $LogDir "$Date.log"
$Archive = Join-Path $Proj "episodes\$Date"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

function Write-Log {
    param([string]$Message, [string]$Level = 'INFO')
    $line = "{0} [{1}] {2}" -f (Get-Date -Format 'HH:mm:ss'), $Level, $Message
    Add-Content -Path $LogFile -Value $line -Encoding utf8
    Write-Output $line
}

function Send-Toast {
    param([string]$Title, [string]$Body)
    try {
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        $icon = New-Object System.Windows.Forms.NotifyIcon
        $icon.Icon = [System.Drawing.SystemIcons]::Information
        $icon.Visible = $true
        $icon.ShowBalloonTip(15000, $Title, $Body, [System.Windows.Forms.ToolTipIcon]::Info)
        Start-Sleep -Seconds 6
        $icon.Dispose()
    } catch {
        Write-Log "notification failed: $($_.Exception.Message)" 'WARN'
    }
}

function Invoke-Step {
    param([string]$Name, [scriptblock]$Action)
    Write-Log "START $Name"
    $out = & $Action 2>&1
    if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
        $out | ForEach-Object { Write-Log "  $_" 'ERR' }
        throw "$Name failed with exit code $LASTEXITCODE"
    }
    $out | ForEach-Object { Write-Log "  $_" }
    Write-Log "OK    $Name"
}

Set-Location $Proj
Write-Log "===== Daily Wrap run for $Date ====="

try {
    # ---- 1. Pull every feed into a single digest -------------------------------
    Invoke-Step 'fetch feeds' { & $Python fetch_news.py --hours 30 }

    # ---- 2. Curate and write the script ---------------------------------------
    if ($SkipCurate) {
        Write-Log 'SKIP  curation (--SkipCurate)' 'WARN'
    } else {
        $before = if (Test-Path 'script.md') { (Get-Item 'script.md').LastWriteTime } else { [datetime]::MinValue }

        $prompt = @"
Produce today's episode of the daily news podcast.

Read brief.md in this directory and follow it exactly. digest.md has already
been generated for you and holds today's articles. Use fetch_article.py to read
the top stories in full before writing.

Write script.md and shownotes.md. Do not ask for confirmation; work to
completion autonomously.
"@

        Invoke-Step 'curate' {
            & $Claude -p $prompt `
                --permission-mode acceptEdits `
                --allowedTools 'Read' 'Write' 'Edit' 'Bash' 'Glob' 'Grep' `
                --add-dir $Proj
        }

        $after = (Get-Item 'script.md').LastWriteTime
        if ($after -le $before) { throw 'curation did not rewrite script.md' }
    }

    # ---- 3. Sanity-check the script before spending time on speech -------------
    $words = ((Get-Content 'script.md' -Raw) -split '\s+').Count
    Write-Log "script is $words words"
    if ($words -lt 900)  { throw "script too short ($words words) - curation likely failed" }
    if ($words -gt 2600) { Write-Log "script unusually long ($words words)" 'WARN' }

    # ---- 4. Render to speech ---------------------------------------------------
    Invoke-Step 'render audio' { & $Python make_episode.py script.md -o episode.mp3 }

    $mp3 = Get-Item 'episode.mp3'
    if ($mp3.Length -lt 500KB) { throw "episode.mp3 is only $($mp3.Length) bytes - render failed" }

    # ---- 5. Deliver and archive ------------------------------------------------
    if (-not (Test-Path $Archive)) { New-Item -ItemType Directory -Path $Archive -Force | Out-Null }
    Copy-Item 'script.md', 'shownotes.md', 'episode.mp3', 'digest.md' -Destination $Archive -Force
    Write-Log "archived to $Archive"

    if (-not $NoDeliver) {
        if (-not (Test-Path $Deliver)) { New-Item -ItemType Directory -Path $Deliver -Force | Out-Null }
        $pretty = Get-Date -Format 'dddd d MMMM'
        Copy-Item 'episode.mp3'   (Join-Path $Deliver "Daily Wrap $Date.mp3") -Force
        Copy-Item 'shownotes.md'  (Join-Path $Deliver "Daily Wrap $Date - notes.txt") -Force
        Write-Log "delivered to $Deliver"

        # Keep the sync folder tidy: 30 days of episodes is plenty.
        Get-ChildItem $Deliver -File |
            Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
            ForEach-Object { Write-Log "pruning $($_.Name)"; Remove-Item $_.FullName -Force }

        $mins = [math]::Round($mp3.Length / 1MB, 1)
        Send-Toast 'Daily Wrap is ready' "$pretty - $words words, $mins MB. In OneDrive\News Podcast."
    }

    Write-Log "===== done ====="
    exit 0
}
catch {
    Write-Log $_.Exception.Message 'ERR'
    Write-Log $_.ScriptStackTrace 'ERR'
    Send-Toast 'Daily Wrap FAILED' "$($_.Exception.Message) - see logs\$Date.log"
    exit 1
}
