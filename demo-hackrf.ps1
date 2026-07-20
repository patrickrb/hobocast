#Requires -Version 5.1
<#
  One command to transmit the demo on a HackRF: digital color+sound BOXCAR TV.
  PowerShell twin of demo-hackrf.sh.

    .\demo-hackrf.ps1            # color bars, or media\channel\* if present
    .\demo-hackrf.ps1 -Gain 30   # HackRF VGA gain override (0-47 dB)

  Receive with an RTL-SDR: .\demo-rx.ps1   (or the Hobocon app). Ctrl-C stops.
#>
param([int]$Gain = 20)

. "$PSScriptRoot\scripts\_config.ps1"

$chan  = Join-Path $RepoRoot 'media\channel'
$exts  = '*.mp4', '*.mkv', '*.mov', '*.ts', '*.cs8'
$clips = @(if (Test-Path -LiteralPath $chan) {
    foreach ($e in $exts) { Get-ChildItem -LiteralPath $chan -Filter $e -File -ErrorAction SilentlyContinue }
})

Write-Host "----------------------------------------------------------------"
Write-Host "  hobocast (HackRF)  .  BOXCAR digital color TV on $([long]($FREQ/1000000)) MHz"
Write-Host "  Point an RTL-SDR receiver here (.\demo-rx.ps1).   Ctrl-C to stop."
Write-Host "----------------------------------------------------------------"

$txhackrf = Join-Path $PSScriptRoot 'scripts\tx-hackrf.ps1'
if ($clips.Count -gt 0) {
    Write-Host "[channel] $($clips.Count) clip(s) in media\channel - streaming on loop"
    & $txhackrf @($clips.FullName) -Gain $Gain
} else {
    Write-Host "[channel] no clips in media\channel - transmitting color bars"
    Write-Host "[tip]     drop any .mp4 into media\channel\ (or run scripts\fetch-commercials.ps1)"
    & $txhackrf -Gain $Gain
}
