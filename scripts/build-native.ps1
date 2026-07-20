#Requires -Version 5.1
<#
  Build the fast C++ BOXCAR receiver (native\boxcar_harness.exe). The pure-Python
  receiver is fine for tests but too slow to decode a full clip in a demo; this is
  the same DSP the phone runs, and it decodes in real time. PowerShell twin of
  build-native.sh.

  Usage: scripts\build-native.ps1   (needs clang++ or g++; the installer adds LLVM)
#>
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

$cxx = $null
foreach ($c in @($env:CXX_OVERRIDE, 'clang++', 'g++', 'c++')) {
    if ($c -and (Get-Command $c -ErrorAction SilentlyContinue)) { $cxx = $c; break }
}
if (-not $cxx) {
    Write-Error "No C++ compiler found. Install LLVM/clang++ (winget install -e --id LLVM.LLVM) or run scripts\install-windows.ps1."
    exit 1
}

$outfile = Join-Path $root 'native\boxcar_harness.exe'
Write-Host "Building with $cxx -> $outfile"
& $cxx -O2 -std=c++17 `
    (Join-Path $root 'native\harness.cpp') (Join-Path $root 'native\boxcar_rx.cpp') `
    -o $outfile
if ($LASTEXITCODE -ne 0) { Write-Error "compile failed (exit $LASTEXITCODE)"; exit 1 }
Write-Host "done. The demo RX scripts will now use it automatically."
