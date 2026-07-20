#Requires -Version 5.1
<#
  Shared configuration + helpers for the hobocast demo scripts on Windows.
  Dot-sourced, not run:   . "$PSScriptRoot\_config.ps1"

  The PowerShell twin of scripts/_config.sh. Same constants, same transmit /
  receive chain:

    ffmpeg (H.264+AAC -> MPEG-TS) -> boxcar.cli -> IQ -> hackrf_transfer
    rtl_sdr -> boxcar.cli rx -> MPEG-TS -> ffplay   (color + sound)

  One Windows-specific wrinkle drives the design: Windows PowerShell 5.1
  mangles raw bytes sent through '|' or '>' (it decodes to text and re-encodes).
  So every byte-critical stage here either writes straight to a file (ffmpeg and
  boxcar.cli both take an output-file argument) or, for the live transmit
  pipelines, runs through cmd.exe, whose pipes are byte-exact. Never pipe binary
  through a PowerShell '|'.

  Override any constant from the environment, e.g.  $env:HOBOCAST_FREQ=915000000
#>

Set-StrictMode -Off
$ErrorActionPreference = 'Stop'

# --- constants (env-overridable, same names as _config.sh) -----------------
$FREQ       = if ($env:HOBOCAST_FREQ)       { [long]$env:HOBOCAST_FREQ }   else { 906000000 }  # 906 MHz ISM
$RATE       = if ($env:HOBOCAST_RATE)       { [long]$env:HOBOCAST_RATE }   else { 2400000 }    # 2.4 Msps
$TXFMT      = if ($env:HOBOCAST_TXFMT)      { $env:HOBOCAST_TXFMT }        else { 'cs8' }      # HackRF: signed 8-bit
$RXFMT      = if ($env:HOBOCAST_RXFMT)      { $env:HOBOCAST_RXFMT }        else { 'cu8' }      # RTL-SDR: unsigned 8-bit
$PACKETS    = if ($env:HOBOCAST_PACKETS)    { [int]$env:HOBOCAST_PACKETS } else { 7 }          # TS packets / BOXCAR frame
$CFO_SEARCH = if ($env:HOBOCAST_CFO_SEARCH) { [int]$env:HOBOCAST_CFO_SEARCH } else { 30000 }   # +/-Hz coarse carrier search
# FEC is on by default; set $env:HOBOCAST_FEC='' to disable. Kept as an arg array
# so an empty value adds no argument (a bare '' would pass an empty argument).
$FEC_RAW    = if ($null -ne $env:HOBOCAST_FEC) { $env:HOBOCAST_FEC } else { '--fec' }
# [string[]] is load-bearing: without it PowerShell unwraps the single-element
# result to a bare string, and splatting a string (@FecArgs) iterates its
# characters ("- - f e c") instead of passing one "--fec" argument.
[string[]]$FecArgs = if ([string]::IsNullOrWhiteSpace($FEC_RAW)) { @() } else { $FEC_RAW -split '\s+' }

# --- repo + python ---------------------------------------------------------
$CfgDir   = $PSScriptRoot
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Test-Have($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }

# Pick the first interpreter that actually runs (skips the Windows Store
# `python3` stub, which resolves but errors out) - same guard as _config.sh.
function Resolve-Python {
    if ($env:PYTHON) { return $env:PYTHON }
    foreach ($cand in @('python', 'py', 'python3')) {
        if (Test-Have $cand) {
            try { & $cand -c 'import sys' *> $null; if ($LASTEXITCODE -eq 0) { return $cand } } catch {}
        }
    }
    return 'python'
}
$Py = Resolve-Python

# Run the BOXCAR CLI from the repo root (so `boxcar` imports resolve). Args that
# are text-only (e.g. `rate`) are safe through PowerShell; binary goes to files.
function Invoke-Boxcar {
    param([Parameter(ValueFromRemainingArguments = $true)] $BoxArgs)
    Push-Location $RepoRoot
    try { & $Py -m boxcar.cli @BoxArgs } finally { Pop-Location }
}

# The payload (transport-stream) bitrate the link carries, for CBR muxing.
function Get-BoxcarRate {
    [long]((Invoke-Boxcar rate @FecArgs --packets $PACKETS | Select-Object -First 1).ToString().Trim())
}

# The fast C++ receiver, if built (scripts\build-native.ps1). Decoding a full
# clip in pure Python is too slow for a demo; this is the same DSP the phone runs.
$Harness = $null
foreach ($h in @("$RepoRoot\native\boxcar_harness.exe", "$RepoRoot\native\boxcar_harness", "$RepoRoot\out\boxcar_harness.exe")) {
    if (Test-Path -LiteralPath $h) { $Harness = $h; break }
}

# Decode an IQ capture ($InFile) to a transport stream ($OutFile). Uses the C++
# harness when available (fast), else the pure-Python CLI (correct but slow).
# Both take file arguments, so no binary crosses a PowerShell pipe. Returns $true
# on success.
$script:BoxcarDecodeWarned = $false
function Invoke-BoxcarDecode {
    param([string]$InFile, [string]$OutFile)
    if ($Harness) {
        $a = @($InFile, $OutFile)
        if ($RXFMT -eq 'cs8')  { $a += '--cs8' }
        if ($FecArgs.Count -gt 0) { $a += '--fec' }
        $a += @('--soft', '--cfo-search', "$CFO_SEARCH", '--packets', "$PACKETS")
        & $Harness @a
    } else {
        if (-not $script:BoxcarDecodeWarned) {
            Write-Host "[note] using the pure-Python decoder (slow). For a fast demo run: scripts\build-native.ps1"
            $script:BoxcarDecodeWarned = $true
        }
        Invoke-Boxcar rx $InFile $OutFile --fmt $RXFMT @FecArgs --packets $PACKETS --soft --cfo-search $CFO_SEARCH
    }
    return ($LASTEXITCODE -eq 0)
}

function Assert-Cmd($name) {
    if (-not (Test-Have $name)) {
        Write-Error "Missing '$name' - run scripts\install-windows.ps1 (Windows), or install-linux.sh / install-mac.sh."
        exit 1
    }
}

# hackrf present? (non-fatal filename checks happen before this so they surface first)
function Assert-HackRF {
    if (-not (Test-Have 'hackrf_info')) { Write-Error "Missing hackrf tools (install PothosSDR)."; exit 1 }
    if (-not ((hackrf_info 2>&1 | Out-String) -match 'Serial number')) {
        Write-Error "No HackRF detected. Plug it in (TX via ANT port), check: hackrf_info"
        exit 1
    }
}

# rtl-sdr present?
function Assert-RtlSdr {
    if (-not (Test-Have 'rtl_sdr')) { Write-Error "Missing rtl_sdr (install PothosSDR)."; exit 1 }
    if (Test-Have 'rtl_test') {
        if (-not ((rtl_test -t 2>&1 | Out-String) -match '(?i)Found|tuner')) {
            Write-Warning "No RTL-SDR detected (rtl_test found none). Plug it in."
        }
    }
}

# ffmpeg encode of one-or-more inputs to a CBR MPEG-TS *file*, sized to the
# BOXCAR link. Writes straight to $OutFile (no PowerShell redirect -> byte-exact).
# $InputArgs is an array of ffmpeg input options/files, e.g. @('-t','6','-i',$clip).
# (An explicit array param, not ValueFromRemainingArguments: repeated -f/-i tokens
# confuse the remaining-args binder.) Video is 320x240 so H.264 fits under the link.
function Invoke-FfmpegTs {
    param([long]$Mux, [string]$OutFile, [string[]]$InputArgs)
    $vbr = [long]($Mux * 6 / 10)          # ~60% video, leaving room for audio + TS overhead
    $buf = [long]($vbr / 2)
    & ffmpeg -hide_banner -loglevel error @InputArgs `
        -vf "scale=320:240:flags=lanczos,setsar=1,fps=30000/1001" -pix_fmt yuv420p `
        -c:v libx264 -profile:v baseline -preset veryfast -g 30 `
        -b:v $vbr -maxrate $vbr -bufsize $buf `
        -c:a aac -b:a 64k -ac 1 -ar 44100 `
        -f mpegts -muxrate $Mux $OutFile
    if ($LASTEXITCODE -ne 0) { throw "ffmpeg failed (exit $LASTEXITCODE)" }
}

# Run a live, byte-exact multi-stage pipeline. PowerShell's '|' would corrupt the
# binary, so the pipeline text is executed by cmd.exe (byte-exact pipes) from the
# repo root. $PipelineText is a cmd.exe command line (already quoted for cmd);
# use $Py / absolute paths inside it. Ctrl-C reaches the children (shared console)
# just like Ctrl-C to a bash pipe. Returns cmd's exit code.
function Invoke-BytePipeline {
    param([Parameter(Mandatory = $true)][string]$PipelineText)
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("hobocast-" + [System.IO.Path]::GetRandomFileName() + ".cmd")
    $body = "@echo off`r`ncd /d `"$RepoRoot`"`r`n$PipelineText`r`n"
    Set-Content -LiteralPath $tmp -Value $body -Encoding Ascii
    try { & cmd.exe /c $tmp; return $LASTEXITCODE }
    finally { Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue }
}

# A cmd-quoted token for the python launcher, for use inside Invoke-BytePipeline.
$PyQuoted = if ($Py -match '\s') { "`"$Py`"" } else { $Py }
$FecCmd   = if ($FecArgs.Count -gt 0) { ($FecArgs -join ' ') } else { '' }

# A private temp directory (auto-cleanable). Callers Remove-Item it when done.
function New-TempDir {
    $d = Join-Path ([System.IO.Path]::GetTempPath()) ("hobocast-" + [System.IO.Path]::GetRandomFileName())
    New-Item -ItemType Directory -Force -Path $d | Out-Null
    return $d
}

# Create a parent directory for an output file path, if it has one.
function New-ParentDir([string]$Path) {
    $p = Split-Path -Parent $Path
    if ($p) { New-Item -ItemType Directory -Force -Path $p | Out-Null }
}

# --- cmd.exe pipeline stage builders (for the live transmit scripts) -------
# These return strings for Invoke-BytePipeline. The ffmpeg encode tail matches
# _config.sh's real-time settings (bufsize = Mux/3, tighter than the file path).
function Get-FfmpegEncodeTail([long]$Mux) {
    $vbr = [long]($Mux * 6 / 10); $buf = [long]($Mux / 3)
    "-vf `"scale=320:240:flags=lanczos,setsar=1,fps=30000/1001`" -pix_fmt yuv420p " +
    "-c:v libx264 -profile:v baseline -preset veryfast -g 30 " +
    "-b:v $vbr -maxrate $vbr -bufsize $buf -c:a aac -b:a 64k -ac 1 -ar 44100 " +
    "-f mpegts -muxrate $Mux -"
}
function Get-BoxcarStreamStage([string]$Fmt) {
    "$PyQuoted -m boxcar.cli stream - - --fmt $Fmt $FecCmd --packets $PACKETS"
}
function Get-HackrfTxStage([int]$Amp, [int]$Gain) {
    "hackrf_transfer -t - -f $FREQ -s $RATE -a $Amp -x $Gain"
}
