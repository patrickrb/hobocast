#Requires -Version 5.1
<#
  Transmit a BOXCAR IQ file (or any video) on a loop via HackRF. A pre-rendered
  .cs8 is looped straight off disk by hackrf_transfer -R - rock-solid, no
  real-time Python. Anything else (a .ts or a video) is rendered to IQ first.
  PowerShell twin of tx-file.sh.

  Usage:  scripts\tx-file.ps1 <file.cs8|file.ts|video.mp4> [-Gain N] [-Amp]
    -Gain  HackRF TX VGA gain 0-47 dB (default 20).
    -Amp   Enable the +~11 dB TX amp (off by default - keep power low).

  Tune your receiver (RTL-SDR + the Hobocon app, or scripts\rx-rtlsdr.ps1) to
  906 MHz. Ctrl-C stops.
#>
param(
    [Parameter(Mandatory = $true)][string]$InputPath,
    [int]$Gain = 20,
    [switch]$Amp
)

. "$PSScriptRoot\_config.ps1"

if (-not (Test-Path -LiteralPath $InputPath)) {
    Write-Error "Usage: tx-file.ps1 <file.cs8|file.ts|video> [-Gain N] [-Amp]"
    exit 1
}

Assert-Cmd hackrf_transfer
Assert-HackRF

$tmp = $null
$iq  = $InputPath
$ext = [System.IO.Path]::GetExtension($InputPath).ToLower()
try {
    if ($ext -notin '.cs8', '.cu8') {          # render .ts / video -> IQ first
        Assert-Cmd ffmpeg
        $tmp = New-TempDir
        $iq  = Join-Path $tmp "tx.$TXFMT"
        $Mux = Get-BoxcarRate
        Write-Host "[render] $InputPath -> $iq"
        if ($ext -eq '.ts') {
            Invoke-Boxcar tx $InputPath $iq --fmt $TXFMT @FecArgs --packets $PACKETS
        } else {
            $x = Join-Path $tmp 'x.ts'
            Invoke-FfmpegTs $Mux $x -InputArgs @('-i', $InputPath)
            Invoke-Boxcar tx $x $iq --fmt $TXFMT @FecArgs --packets $PACKETS
        }
        if ($LASTEXITCODE -ne 0) { Write-Error "render failed"; exit 1 }
    }

    $ampv   = if ($Amp) { 1 } else { 0 }
    $ampTxt = if ($Amp) { 'on' } else { 'off' }
    Write-Host ""
    Write-Host "  BOXCAR digital TV -> HackRF (looping from disk)"
    Write-Host "  file=$(Split-Path -Leaf $iq)  freq=$FREQ Hz  rate=$RATE sps  gain=$Gain dB  amp=$ampTxt"
    Write-Host "  Tune your RTL-SDR receiver to $([long]($FREQ/1000000)) MHz. Ctrl-C to stop."
    Write-Host ""
    # -R repeats the file forever; hackrf streams it from disk (no length cap).
    & hackrf_transfer -t $iq -f $FREQ -s $RATE -a $ampv -x $Gain -R
} finally {
    if ($tmp) { Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue }
}
