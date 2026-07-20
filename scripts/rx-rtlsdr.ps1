#Requires -Version 5.1
<#
  Receive BOXCAR off an RTL-SDR, decode to MPEG-TS, and play it - color + sound.
  Captures a chunk, decodes, and plays it (the pure-Python receiver isn't
  real-time at 2.4 Msps; the real-time receiver is the C++ core the Hobocon app
  runs, built with scripts\build-native.ps1). PowerShell twin of rx-rtlsdr.sh.

  Usage:  scripts\rx-rtlsdr.ps1 [-Seconds N] [-Gain N|auto] [-Loop] [-Keep FILE]
    -Seconds  capture length per chunk (default 6)
    -Gain     RTL-SDR tuner gain dB (default 40; 'auto' for AGC)
    -Loop     capture/decode/play repeatedly until Ctrl-C
    -Keep     also write the recovered .ts to FILE

  Tune the transmitter to 906 MHz first (scripts\tx-file.ps1 / tx-hackrf.ps1).
#>
param([int]$Seconds = 6, $Gain = 40, [switch]$Loop, [string]$Keep)

. "$PSScriptRoot\_config.ps1"

Assert-Cmd rtl_sdr
Assert-Cmd ffplay
Assert-RtlSdr

$gainArgs = if ("$Gain" -eq 'auto') { @() } else { @('-g', "$Gain") }
$nsamp    = [long]($RATE * $Seconds)
$tmp      = New-TempDir

function Invoke-GrabAndPlay {
    $cap = Join-Path $tmp "cap.$RXFMT"
    $ts  = Join-Path $tmp 'out.ts'
    Write-Host "[rx] capturing ${Seconds}s @ $([long]($FREQ/1000000)) MHz ..."
    & rtl_sdr -f $FREQ -s $RATE @gainArgs -n $nsamp $cap 2>$null   # rtl_sdr writes the file itself (byte-safe)
    Write-Host "[rx] decoding BOXCAR ..."
    if (-not (Invoke-BoxcarDecode $cap $ts)) { Write-Host "[rx] no frames decoded"; return }
    if ($Keep) { Copy-Item -LiteralPath $ts -Destination $Keep -Force; Write-Host "[rx] saved -> $Keep" }
    Write-Host "[rx] playing ..."
    & ffplay -hide_banner -loglevel warning -autoexit $ts
}

try {
    if ($Loop) {
        Write-Host "Looping capture/decode/play. Ctrl-C to stop."
        while ($true) { Invoke-GrabAndPlay }
    } else {
        Invoke-GrabAndPlay
    }
} finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
