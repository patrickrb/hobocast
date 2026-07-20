#Requires -Version 5.1
<#
  Real-time BOXCAR transmit to a HackRF: encode video live and modulate on the
  fly. PowerShell twin of tx-hackrf.sh.

    ffmpeg (H.264+AAC, CBR TS) -> boxcar.cli stream -> hackrf_transfer

  Any-length video, no pre-render. The TS is muxed CBR at the BOXCAR payload rate
  so the modulator self-paces to the radio. If your CPU can't modulate in real
  time (you'll hear hackrf underruns), pre-render instead:
    scripts\render-iq.ps1 <video> 0 <dur> out.cs8 ; scripts\tx-file.ps1 out.cs8

  The live 3-stage pipe carries raw IQ bytes, which Windows PowerShell would
  corrupt through '|', so it runs through cmd.exe (byte-exact pipes) - see
  Invoke-BytePipeline in _config.ps1.

  Usage:  scripts\tx-hackrf.ps1 [input ...] [-Gain N] [-Amp]
    input   video file(s), looped forever. Omit for color bars.

  Tune the receiver to 906 MHz. Ctrl-C stops.
#>
param(
    [int]$Gain = 20,
    [switch]$Amp,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Inputs
)

. "$PSScriptRoot\_config.ps1"

# Drop a bare "bars" token (bash accepted it as a no-op) and keep real inputs.
$clips = @($Inputs | Where-Object { $_ -and $_ -ne 'bars' })

Assert-Cmd ffmpeg
Assert-Cmd hackrf_transfer
Assert-HackRF
$Mux  = Get-BoxcarRate
$ampv = if ($Amp) { 1 } else { 0 }

$tmp = $null
try {
    # Build the ffmpeg source: a concat of looping inputs, or color bars.
    if ($clips.Count -eq 0) {
        Write-Host "[src] no input - transmitting color bars + 440 Hz tone"
        $src = '-re -f lavfi -i "smptehdbars=size=320x240:rate=30000/1001" -f lavfi -i "sine=frequency=440"'
    } else {
        foreach ($f in $clips) { if (-not (Test-Path -LiteralPath $f)) { Write-Error "Not found: $f"; exit 1 } }
        Write-Host "[src] $($clips.Count) input(s), looped: $($clips -join ', ')"
        if ($clips.Count -eq 1) {
            $abs = (Resolve-Path -LiteralPath $clips[0]).Path
            $src = "-stream_loop -1 -re -i `"$abs`""
        } else {
            # concat demuxer wants forward slashes and 'file' lines.
            $tmp  = New-TempDir
            $list = Join-Path $tmp 'playlist.txt'
            $lines = foreach ($f in $clips) {
                $abs = (Resolve-Path -LiteralPath $f).Path.Replace('\', '/')
                "file '$abs'"
            }
            Set-Content -LiteralPath $list -Value $lines -Encoding Ascii
            $src = "-stream_loop -1 -re -f concat -safe 0 -i `"$list`""
        }
    }

    $ampTxt = if ($Amp) { 'on' } else { 'off' }
    Write-Host ""
    Write-Host "  BOXCAR digital TV -> HackRF (real-time)"
    Write-Host "  freq=$FREQ Hz  rate=$RATE sps  gain=$Gain dB  amp=$ampTxt"
    Write-Host "  link payload=$([long]($Mux/1000)) kbit/s (CBR)"
    Write-Host "  Tune your RTL-SDR receiver to $([long]($FREQ/1000000)) MHz. Ctrl-C to stop."
    Write-Host ""

    $pipeline = "ffmpeg -hide_banner -loglevel error $src $(Get-FfmpegEncodeTail $Mux)" +
                " | $(Get-BoxcarStreamStage $TXFMT)" +
                " | $(Get-HackrfTxStage $ampv $Gain)"
    Invoke-BytePipeline $pipeline | Out-Null
} finally {
    if ($tmp) { Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue }
}
