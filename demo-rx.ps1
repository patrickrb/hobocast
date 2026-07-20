#Requires -Version 5.1
<#
  One command to receive the demo on an RTL-SDR and play it: capture -> decode
  BOXCAR -> color + sound. PowerShell twin of demo-rx.sh.

    .\demo-rx.ps1            # capture a few seconds, decode, play
    .\demo-rx.ps1 -Loop      # keep grabbing successive chunks

  Point a transmitter at 906 MHz first (.\demo-hackrf.ps1 on another machine).
  Any extra arguments are forwarded to scripts\rx-rtlsdr.ps1.
#>
& "$PSScriptRoot\scripts\rx-rtlsdr.ps1" @args
