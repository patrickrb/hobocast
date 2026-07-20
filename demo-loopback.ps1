#Requires -Version 5.1
<#
  The whole demo with NO radio: encode a clip, push it through BOXCAR, decode it
  back, and play the result. Proves the digital chain end-to-end on any laptop -
  the same bytes come out that went in. Great for a talk when you can't (or
  shouldn't) transmit. PowerShell twin of demo-loopback.sh.

    ffmpeg -> MPEG-TS -> boxcar.cli tx -> IQ -> boxcar.cli rx -> MPEG-TS -> ffplay

  Usage:  .\demo-loopback.ps1 [input.mp4]   (color bars + tone if omitted)
          .\demo-loopback.ps1 -NoPlay       (skip playback; just prove the chain)
#>
param([string]$InputPath, [switch]$NoPlay)

. "$PSScriptRoot\scripts\_config.ps1"

Assert-Cmd ffmpeg
$Mux = Get-BoxcarRate
$Out = Join-Path $RepoRoot 'out'; New-Item -ItemType Directory -Force -Path $Out | Out-Null
$Src = Join-Path $Out 'loopback_src.ts'
$Iq  = Join-Path $Out "loopback.$RXFMT"
$Got = Join-Path $Out 'loopback_out.ts'

Write-Host "----------------------------------------------------------------"
Write-Host "  hobocast loopback  -  digital color TV through BOXCAR, no radio"
Write-Host "  link payload = $([long]($Mux/1000)) kbit/s"
Write-Host "----------------------------------------------------------------"

Write-Host "[1/4] encode source -> MPEG-TS"
if ($InputPath) {
    if (-not (Test-Path -LiteralPath $InputPath)) { Write-Error "Not found: $InputPath"; exit 1 }
    Invoke-FfmpegTs $Mux $Src -InputArgs @('-t', '6', '-i', $InputPath)
} else {
    Invoke-FfmpegTs $Mux $Src -InputArgs @(
        '-f', 'lavfi', '-i', 'smptehdbars=size=320x240:rate=30000/1001:duration=6',
        '-f', 'lavfi', '-i', 'sine=frequency=440:duration=6')
}

Write-Host "[2/4] modulate BOXCAR  ($Src -> $Iq)"
Invoke-Boxcar tx $Src $Iq --fmt $RXFMT @FecArgs --packets $PACKETS
if ($LASTEXITCODE -ne 0) { Write-Error "boxcar tx failed"; exit 1 }

Write-Host "[3/4] demodulate BOXCAR  ($Iq -> $Got)"
$ok = Invoke-BoxcarDecode $Iq $Got

# Byte-exact comparison (channel-free, so it should always match).
$identical = $false
if ((Test-Path -LiteralPath $Src) -and (Test-Path -LiteralPath $Got)) {
    $identical = (Get-FileHash -LiteralPath $Src -Algorithm SHA256).Hash -eq `
                 (Get-FileHash -LiteralPath $Got -Algorithm SHA256).Hash
}
if ($identical) {
    Write-Host "[4/4] recovered byte-exact ($((Get-Item $Got).Length) bytes). Playing ..."
} else {
    Write-Host "[4/4] recovered with differences (channel-free, so unexpected) - playing anyway."
}

if ($NoPlay) {
    Write-Host "(-NoPlay) recovered stream is at $Got"
} elseif (Test-Have ffplay) {
    & ffplay -hide_banner -loglevel warning -autoexit $Got
} else {
    Write-Host "(install ffplay to watch; recovered stream is at $Got)"
}
