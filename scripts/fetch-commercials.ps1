#Requires -Version 5.1
<#
  Populate media\channel\ with a playlist of 1990s TV commercials for the demo
  (demo-hackrf.ps1 / tx-cycle.ps1 play everything in that folder). Source: the
  Internet Archive "Collection of 90s Commercials". PowerShell twin of
  fetch-commercials.sh.

  Clips are hosted by archive.org and remain their owners' copyright; kept out of
  git (see .gitignore) and fetched on demand for a local, low-power bench demo.

  Usage:  scripts\fetch-commercials.ps1 [count]   (default 14)
  Idempotent: existing clips are skipped.
#>
param([int]$Count = 14)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$dest = Join-Path $root 'media\channel'

$base     = 'https://archive.org/download/Collectionof90sCommercials'
$episodes = @(
    'S01.E1', 'S01.E2', 'S01.E3', 'S01.E4', 'S01.E5', 'S01.E6', 'S01.E7', 'S01.E8', 'S01.E9',
    'S01.E10', 'S01.E11', 'S01.E12', 'S01.E16', 'S01.E29', 'S01.E30', 'S01.E31', 'S02.E4', 'S02.E8')

New-Item -ItemType Directory -Force -Path $dest | Out-Null
Write-Host "Fetching up to $Count 90s commercial(s) into $dest"

$n = 0; $got = 0
foreach ($ep in $episodes) {
    if ($got -ge $Count) { break }
    $n++
    $out = Join-Path $dest ("commercial-{0:D2}.mp4" -f $n)
    if ((Test-Path -LiteralPath $out) -and (Get-Item $out).Length -gt 100000) {
        Write-Host ("  skip commercial-{0:D2}.mp4 (already present)" -f $n); $got++; continue
    }
    $url = "$base/90s%20Commercials%20-%20$ep.mp4"
    try { Invoke-WebRequest -Uri $url -OutFile $out -TimeoutSec 90 -UseBasicParsing } catch {}
    $sz = if (Test-Path -LiteralPath $out) { (Get-Item $out).Length } else { 0 }
    if ($sz -lt 100000) {
        Remove-Item -LiteralPath $out -ErrorAction SilentlyContinue
        Write-Host "  skip $ep (download failed / too small)"
    } else {
        Write-Host ("  ok   commercial-{0:D2}.mp4  ({1} KB)" -f $n, [long]($sz / 1024)); $got++
    }
}

Write-Host ""
Write-Host "$got clip(s) ready in $dest"
Write-Host "Now run:  .\demo-hackrf.ps1   (transmits media\channel\*.mp4 on 906 MHz)"
