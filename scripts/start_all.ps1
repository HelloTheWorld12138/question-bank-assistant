$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

function Write-Step($Message) {
  Write-Host ""
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function Find-CommandPath($Name) {
  $command = Get-Command $Name -ErrorAction SilentlyContinue
  if ($command) {
    return $command.Source
  }
  return $null
}

Write-Step "Preparing Python environment"
$SystemPython = Find-CommandPath "python.exe"
if (-not $SystemPython) {
  $SystemPython = Find-CommandPath "python"
}
if (-not $SystemPython) {
  throw "Python was not found. Install Python 3.10+ or add python to PATH."
}

$VenvDir = Join-Path $Root ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvScripts = Join-Path $VenvDir "Scripts"
if (-not (Test-Path $VenvPython)) {
  & $SystemPython -m venv $VenvDir
}

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $Root "requirements.txt")

$env:PATH = "$VenvScripts;$env:PATH"

Write-Step "Preparing Pandoc"
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\install_pandoc.ps1")

Write-Step "Detecting optional local integrations"
$OpenCodeDir = Join-Path $Root "tools\opencode"
$OpenCodeBin = Join-Path $OpenCodeDir "node_modules\.bin"
if (Test-Path $OpenCodeBin) {
  $env:PATH = "$OpenCodeBin;$env:PATH"
}

Write-Step "Checking available features"
$VerifyLines = & $VenvPython -c "from app.agent import opencode_available; from app.math_ocr import formula_ocr_available; print(f'agent={opencode_available()}'); print(f'formula_ocr={formula_ocr_available()}')"
$VerifyText = $VerifyLines -join "`n"
Write-Host $VerifyText
if ($VerifyText -notmatch "agent=True") {
  Write-Host "OpenCode is not configured. Word import will use offline rules and teacher review." -ForegroundColor Yellow
}
if ($VerifyText -notmatch "formula_ocr=True") {
  Write-Host "Formula OCR is not configured. Ordinary Word files still work; image formulas require manual LaTeX review." -ForegroundColor Yellow
}

Write-Step "Starting Physics Question Bank Assistant"
Write-Host "Open this address if the browser does not open automatically:"
Write-Host "http://127.0.0.1:8000"

$ExistingServers = Get-CimInstance Win32_Process |
  Where-Object {
    $_.CommandLine -and
    $_.CommandLine -like "*uvicorn app.main:app*" -and
    $_.CommandLine -like "*$Root*"
  }
foreach ($Server in $ExistingServers) {
  Write-Host "Stopping previous local server process $($Server.ProcessId)." -ForegroundColor Yellow
  Stop-Process -Id $Server.ProcessId -Force
}

Start-Process "http://127.0.0.1:8000"
& $VenvPython -m uvicorn app.main:app --host 127.0.0.1 --port 8000
