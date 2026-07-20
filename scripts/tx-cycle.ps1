#Requires -Version 5.1
<#
  Rotate through a directory of clips, each transmitted for HOLD seconds, then on
  to the next, forever. Any length clips are fine (no cyclic DDR cap). Accepts
  .cs8 IQ files (looped from disk) or videos (rendered on the fly). PowerShell
  twin of tx-cycle.sh.

  Usage:  scripts\tx-cycle.ps1 [-Dir media\channel] [-Hold 30] [-Gain 20]
#>
param([string]$Dir, [int]$Hold = 30, [int]$Gain = 20)

. "$PSScriptRoot\_config.ps1"

if (-not $Dir) { $Dir = Join-Path $RepoRoot 'media\channel' }
if (-not (Test-Path -LiteralPath $Dir)) { Write-Error "Directory not found: $Dir (drop .cs8/.mp4 files in it)"; exit 1 }

$exts  = '*.cs8', '*.mp4', '*.mkv', '*.mov', '*.ts'
$clips = @(foreach ($e in $exts) { Get-ChildItem -LiteralPath $Dir -Filter $e -File -ErrorAction SilentlyContinue })
if ($clips.Count -eq 0) { Write-Error "No clips in $Dir"; exit 1 }

Write-Host "Cycling $($clips.Count) clip(s) from $Dir, ${Hold}s each, forever. Ctrl-C to stop."
$txfile = Join-Path $CfgDir 'tx-file.ps1'
$child  = $null
try {
    while ($true) {
        foreach ($clip in $clips) {
            Write-Host "[$((Get-Date).ToString('HH:mm:ss'))] $($clip.Name) for ${Hold}s"
            $child = Start-Process -FilePath 'powershell' -PassThru -ArgumentList @(
                '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $txfile, $clip.FullName, '-Gain', $Gain)
            Start-Sleep -Seconds $Hold
            # Kill the whole tree (/T) so hackrf_transfer dies with its launcher.
            taskkill /PID $child.Id /T /F 2>$null | Out-Null
            $child = $null
            Start-Sleep -Seconds 1   # let the USB interface release before the next claim
        }
    }
} finally {
    if ($child -and -not $child.HasExited) { taskkill /PID $child.Id /T /F 2>$null | Out-Null }
}
