#Requires -Version 5.1
<#
  Broadcast a LIVE OBS feed as digital BOXCAR TV on the HackRF. PowerShell twin
  of tx-obs.sh.

    OBS --(MPEG-TS over local UDP)--> ffmpeg (re-mux CBR) --> boxcar.cli stream
        --> hackrf_transfer

  Start THIS first, then start OBS's UDP output. Because BOXCAR carries a normal
  MPEG-TS, OBS can feed H.264+AAC straight through - color and sound. The live
  binary pipe runs through cmd.exe (byte-exact) - see Invoke-BytePipeline.

  Usage:  scripts\tx-obs.ps1 [-Port N] [-Gain N] [-Amp] [-Record [FILE]]

  OBS: Settings -> Output (Advanced, Recording tab):
    Type: Custom Output (FFmpeg);  Output to URL: udp://127.0.0.1:1234?pkt_size=1316
    Container: mpegts;  Video: h264 ~500 kbps;  Keyframe interval: 30
    Audio: aac 64k;  Rescale: 320x240;  Video FPS: 30000/1001
  Then click Start Recording.  Ctrl-C here to stop.
#>
param(
    [int]$Port = 1234,
    [int]$Gain = 20,
    [switch]$Amp,
    [switch]$Record,
    [string]$RecordFile
)

. "$PSScriptRoot\_config.ps1"

Assert-Cmd ffmpeg
Assert-Cmd hackrf_transfer
Assert-HackRF
$Mux  = Get-BoxcarRate
$ampv = if ($Amp) { 1 } else { 0 }
$in   = "udp://127.0.0.1:${Port}?fifo_size=1000000&overrun_nonfatal=1"

Write-Host ""
Write-Host "  OBS -> HackRF live  .  BOXCAR digital TV on $([long]($FREQ/1000000)) MHz"
Write-Host "  Listening for OBS on udp://127.0.0.1:${Port}  (Custom FFmpeg output, mpegts)"
Write-Host "  freq=$FREQ Hz  rate=$RATE sps  gain=$Gain dB  link=$([long]($Mux/1000)) kbit/s"
Write-Host "  Tune your RTL-SDR receiver. Ctrl-C to stop."
Write-Host ""

# Optional byte-exact recording branch (mirrors the bash -map 0 -c copy tee).
$rec = ''
if ($Record) {
    if (-not $RecordFile) {
        # Date.now() isn't available in workflow scripts, but this is a normal
        # interactive script, so a timestamped default name is fine here.
        $RecordFile = "obs-broadcast-$((Get-Date).ToString('yyyyMMdd-HHmmss')).ts"
    }
    Write-Host "[rec] byte-exact copy -> $RecordFile"
    $rec = "-map 0 -c copy -f mpegts `"$RecordFile`" "
}

$pipeline = "ffmpeg -hide_banner -loglevel error -i `"$in`" $rec$(Get-FfmpegEncodeTail $Mux)" +
            " | $(Get-BoxcarStreamStage $TXFMT)" +
            " | $(Get-HackrfTxStage $ampv $Gain)"
Invoke-BytePipeline $pipeline | Out-Null
