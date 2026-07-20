#Requires -Version 5.1
<#
  One-time toolchain install for the hobocast demo on Windows.

  The counterpart to scripts/install-mac.sh / install-linux.sh. Two things on
  Windows can't be a single package-manager line the way brew/apt are, so this
  script does the automatable parts and *guides* the rest:

    python + numpy    the BOXCAR modem itself          -> winget (automated)
    ffmpeg (+ffplay)  encode/decode/play H.264+AAC     -> winget (automated)
    LLVM (clang++)    build the fast C++ decoder        -> winget (automated)
    git (optional)    for the .sh script variants       -> winget (automated)
    rtl-sdr + hackrf  the SDR command-line tools        -> PothosSDR (guided)
    WinUSB driver     let the tools claim the dongle     -> Zadig (guided)

  The demos run natively in PowerShell (.\demo-loopback.ps1, etc.) - Git Bash is
  optional, only for the .sh variants.

  The Zadig driver step is the Windows analog of the Linux DVB blacklist
  (scripts/install-linux.sh) - libusb-based tools can't open the RTL2832U until
  its driver is WinUSB instead of the stock DVB/RTL driver. Same for the HackRF.

  Idempotent. winget is built into Windows 10/11 (the "App Installer").

  Usage (from the repo root):
    powershell -ExecutionPolicy Bypass -File scripts\install-windows.ps1

  You do NOT need any radio to try hobocast - see the note at the end for the
  pure-software loopback, which runs on a bare Python + numpy.
#>

$ErrorActionPreference = 'Stop'

function Have($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }

# Resolve a working Python launcher (skip the Windows Store `python3` stub, which
# resolves but errors - the same guard scripts/_config.sh uses).
function Resolve-Python {
    foreach ($cand in @('python', 'py', 'python3')) {
        if (Have $cand) {
            try {
                & $cand -c 'import sys' *> $null
                if ($LASTEXITCODE -eq 0) { return $cand }
            } catch {}
        }
    }
    return $null
}

# winget install that treats "already installed" as success, mirroring the
# `|| true` in the bash installers.
function Winget-Install($id, $label) {
    Write-Host "  - $label ($id)"
    try {
        winget install -e --id $id --accept-source-agreements --accept-package-agreements --silent 2>&1 |
            ForEach-Object { "      $_" } | Write-Host
    } catch {
        Write-Host "      (winget reported an issue; continuing - it may already be installed)"
    }
}

if (-not (Have 'winget')) {
    Write-Error @"
winget not found. It ships with Windows 10/11 as the "App Installer" - get it from
the Microsoft Store, then re-run this script. (Or install the tools by hand:
Python, FFmpeg, Git, LLVM, plus the PothosSDR bundle for rtl_sdr/hackrf.)
"@
    exit 1
}

Write-Host "=== [1/4] winget install (python, ffmpeg, git, llvm) ==="
Winget-Install 'Python.Python.3.12' 'Python 3.12'
Winget-Install 'Gyan.FFmpeg'        'FFmpeg (includes ffplay)'
Winget-Install 'LLVM.LLVM'          'LLVM/clang++ (builds the fast C++ decoder)'
Winget-Install 'Git.Git'            'Git (optional - only for the .sh script variants)'

Write-Host ""
Write-Host "=== [2/4] python deps (numpy) ==="
# winget-installed tools land on PATH only in NEW shells, so re-probe common
# locations if the freshly installed python isn't visible in this session yet.
$py = Resolve-Python
if (-not $py) {
    foreach ($guess in @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe"
    )) { if (Test-Path $guess) { $py = $guess; break } }
}
if ($py) {
    & $py -m pip install --user --upgrade numpy
    & $py -c "import numpy; print('numpy', numpy.__version__)"
} else {
    Write-Host "  numpy: skipped - open a NEW terminal and run:  python -m pip install --user numpy"
}

Write-Host ""
Write-Host "=== [3/4] SDR command-line tools (rtl_sdr, hackrf_transfer) ==="
if ((Have 'rtl_sdr') -and (Have 'hackrf_transfer')) {
    Write-Host "  found rtl_sdr and hackrf_transfer on PATH - good."
} elseif (Have 'choco') {
    Write-Host "  Chocolatey detected - installing the PothosSDR bundle:"
    try { choco install -y pothossdr } catch { Write-Host "  (choco install failed; use the manual bundle below)" }
} else {
    Write-Host @"
  rtl_sdr / hackrf_transfer not found. There is no clean winget package for the
  SDR command-line tools; install the PothosSDR bundle (it ships rtl_sdr.exe,
  rtl_test.exe, hackrf_transfer.exe, hackrf_info.exe and friends):

      https://github.com/pothosware/PothosSDR/wiki/Tutorial   (download the
      "PothosSDR Windows Installer", then add its  bin\  folder to your PATH)

  Or, if you use Chocolatey:   choco install pothossdr
"@
}

Write-Host ""
Write-Host "=== [4/4] USB driver (Zadig) - required before any dongle will open ==="
Write-Host @"
  Windows binds the stock DVB/RTL driver to the RTL-SDR (and nothing to a bare
  HackRF), so libusb-based tools can't claim the device. Fix it once with Zadig
  - this is the Windows analog of the Linux DVB blacklist:

    1. Download & run Zadig:  https://zadig.akeo.ie
    2. Plug in the RTL-SDR. In Zadig:  Options -> List All Devices.
    3. Select "Bulk-In, Interface (Interface 0)" (or "RTL2832U"), pick the
       WinUSB driver in the right box, and click "Replace Driver".
    4. For a HackRF: plug it in and install WinUSB for it the same way.

  (Do this per physical USB port. Re-plug the device afterward.)
"@

# Final summary - mirrors install-mac.sh / install-linux.sh, but the demo entry
# points are Git Bash scripts, so point there.
$ffmpeg  = if (Have 'ffmpeg')          { (Get-Command ffmpeg).Source }          else { 'not found (open a new terminal)' }
$hackrf  = if (Have 'hackrf_transfer') { (Get-Command hackrf_transfer).Source } else { 'not found - install PothosSDR (step 3)' }
$rtlsdr  = if (Have 'rtl_sdr')         { (Get-Command rtl_sdr).Source }         else { 'not found - install PothosSDR (step 3)' }

Write-Host ""
Write-Host "Install complete (open a NEW terminal so freshly installed tools are on PATH)."
Write-Host "  ffmpeg / ffplay : $ffmpeg"
Write-Host "  hackrf_transfer : $hackrf"
Write-Host "  rtl_sdr         : $rtlsdr"
Write-Host ""
Write-Host "No radio needed - the whole chain in pure Python (works in this PowerShell):"
Write-Host "    python demos\loopback.py        # color image through BOXCAR, byte-exact"
Write-Host "    python demos\video_loopback.py  # real H.264+AAC color video+audio"
Write-Host ""
Write-Host "The demo scripts run natively in PowerShell, from the repo root:"
Write-Host "    .\demo-loopback.ps1   # encode -> BOXCAR -> decode -> play, no radio"
Write-Host "    .\demo-hackrf.ps1     # transmit (HackRF)"
Write-Host "    .\demo-rx.ps1         # receive  (RTL-SDR)"
