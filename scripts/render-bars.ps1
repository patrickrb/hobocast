#Requires -Version 5.1
<#
  Render color bars + a 440 Hz tone to a BOXCAR IQ file (color AND sound - the
  whole point of going digital). PowerShell twin of render-bars.sh.

  Usage:   scripts\render-bars.ps1 [out.cs8] [dur_s]
  Example: scripts\render-bars.ps1 media\bars.cs8 10
#>
param([string]$OutFile = 'media\bars.cs8', [int]$Duration = 10)

. "$PSScriptRoot\_config.ps1"

Assert-Cmd ffmpeg
New-ParentDir $OutFile

$Mux = Get-BoxcarRate
$tmp = New-TempDir
$ts  = Join-Path $tmp 'bars.ts'
try {
    Write-Host "[1/2] color bars + 440 Hz tone -> MPEG-TS @ $([long]($Mux/1000)) kbit/s CBR (${Duration}s)"
    Invoke-FfmpegTs $Mux $ts -InputArgs @(
        '-f', 'lavfi', '-i', "smptehdbars=size=320x240:rate=30000/1001:duration=$Duration",
        '-f', 'lavfi', '-i', "sine=frequency=440:duration=$Duration")

    Write-Host "[2/2] modulate BOXCAR -> $OutFile ($TXFMT)"
    Invoke-Boxcar tx $ts $OutFile --fmt $TXFMT @FecArgs --packets $PACKETS
    if ($LASTEXITCODE -ne 0) { Write-Error "boxcar tx failed"; exit 1 }
} finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
$kb = [long]((Get-Item $OutFile).Length / 1024)
Write-Host "    done: $kb KB - transmit with: scripts\tx-file.ps1 $OutFile"
