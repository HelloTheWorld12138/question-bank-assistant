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

function Find-Pnpm {
  $system = Find-CommandPath "pnpm.cmd"
  if ($system) {
    return $system
  }
  $bundled = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\bin\pnpm.cmd"
  if (Test-Path $bundled) {
    return $bundled
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

Write-Step "Preparing local formula OCR"
if (-not $env:FORMULA_OCR_COMMAND) {
  $LatexOcr = Find-CommandPath "latexocr.exe"
  if (-not $LatexOcr) {
    $LatexOcr = Find-CommandPath "latexocr"
  }
  $Pix2Tex = Find-CommandPath "pix2tex.exe"
  if (-not $Pix2Tex) {
    $Pix2Tex = Find-CommandPath "pix2tex"
  }
  if (-not $LatexOcr -and -not $Pix2Tex) {
    Write-Host "latexocr/pix2tex was not found. Installing pix2tex. First install may take a while." -ForegroundColor Yellow
    & $VenvPython -m pip install pix2tex
  }
}

Write-Step "Preparing local opencode agent"
$OpenCodeDir = Join-Path $Root "tools\opencode"
$OpenCodeBin = Join-Path $OpenCodeDir "node_modules\.bin"
$ProjectOpenCode = Join-Path $OpenCodeBin "opencode.cmd"

if (-not $env:QUESTION_AGENT_COMMAND) {
  if (-not (Test-Path $ProjectOpenCode) -and -not (Find-CommandPath "opencode.cmd") -and -not (Find-CommandPath "opencode")) {
    $Pnpm = Find-Pnpm
    if (-not $Pnpm) {
      throw "pnpm was not found. Install Node.js/pnpm or set QUESTION_AGENT_COMMAND manually."
    }
    if (-not (Test-Path $OpenCodeDir)) {
      New-Item -ItemType Directory -Path $OpenCodeDir | Out-Null
    }
    $PackageJson = Join-Path $OpenCodeDir "package.json"
    if (-not (Test-Path $PackageJson)) {
      @'
{
  "private": true,
  "dependencies": {}
}
'@ | Set-Content -Encoding UTF8 $PackageJson
    }
    Write-Host "opencode CLI was not found. Installing opencode-ai. First install needs network." -ForegroundColor Yellow
    & $Pnpm --dir $OpenCodeDir add opencode-ai
  }
}

if (Test-Path $OpenCodeBin) {
  $env:PATH = "$OpenCodeBin;$env:PATH"
}

Write-Step "Verifying local integrations"
$VerifyLines = & $VenvPython -c "from app.agent import opencode_available; from app.math_ocr import formula_ocr_available; print(f'agent={opencode_available()}'); print(f'formula_ocr={formula_ocr_available()}')"
$VerifyText = $VerifyLines -join "`n"
Write-Host $VerifyText
if ($VerifyText -notmatch "agent=True") {
  throw "Local opencode agent is not connected. Make sure opencode CLI works or set QUESTION_AGENT_COMMAND."
}
if ($VerifyText -notmatch "formula_ocr=True") {
  throw "Local formula OCR is not connected. Make sure latexocr/pix2tex works or set FORMULA_OCR_COMMAND."
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
