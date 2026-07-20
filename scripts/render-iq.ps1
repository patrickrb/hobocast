#Requires -Version 5.1
<#
  Trim + encode a video to a BOXCAR IQ file for looped HackRF transmit. There is
  NO cyclic DDR size cap here: hackrf_transfer streams the IQ from disk, so clips
  can be any length. The TS is muxed CBR at the BOXCAR payload rate so looped
  playback stays in sync. PowerShell twin of render-iq.sh.

  Usage:   scripts\render-iq.ps1 <input> <start_s> <dur_s> <out.cs8>
  Example: scripts\render-iq.ps1 media\bbb-trailer.mp4 10 30 media\bbb.cs8
#>
param(
    [Parameter(Mandatory = $true)][string]$InputPath,
    [Parameter(Mandatory = $true)][string]$Start,
    [Parameter(Mandatory = $true)][string]$Duration,
    [Parameter(Mandatory = $true)][string]$OutFile
)

. "$PSScriptRoot\_config.ps1"

Assert-Cmd ffmpeg
if (-not (Test-Path -LiteralPath $InputPath)) { Write-Error "Input not found: $InputPath"; exit 1 }
New-ParentDir $OutFile

$Mux = Get-BoxcarRate
$tmp = New-TempDir
$ts  = Join-Path $tmp 'clip.ts'
try {
    Write-Host "[1/2] encode $InputPath [${Start}s +${Duration}s] -> MPEG-TS @ $([long]($Mux/1000)) kbit/s CBR"
    Invoke-FfmpegTs $Mux $ts -InputArgs @('-ss', "$Start", '-t', "$Duration", '-i', $InputPath)

    Write-Host "[2/2] modulate BOXCAR -> $OutFile ($TXFMT)"
    Invoke-Boxcar tx $ts $OutFile --fmt $TXFMT @FecArgs --packets $PACKETS
    if ($LASTEXITCODE -ne 0) { Write-Error "boxcar tx failed"; exit 1 }
} finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
$kb = [long]((Get-Item $OutFile).Length / 1024)
Write-Host "    done: $kb KB - loop it with: scripts\tx-file.ps1 $OutFile"
