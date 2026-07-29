param(
    [string]$Dist = (Join-Path (Split-Path -Parent $PSScriptRoot) "dist"),
    [string]$AppName = "题搭子",
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$Runtime = Join-Path $Dist "$AppName\_internal"
$Required = @(
    "static\index.html",
    "data\knowledge.yaml",
    "templates\a4_single.docx",
    "tools\pandoc\pandoc.exe",
    "tools\officecli\officecli-win-x64.exe",
    "tools\ruby\bin\ruby.exe",
    "third_party\mathtype_to_mathml\convert.rb",
    "third_party\mathtype_to_mathml\bindata-2.4.15.gem",
    "third_party\mathtype_to_mathml\ruby-ole-1.2.13.1.gem",
    "third_party\mathtype_to_mathml\mathtype_to_mathml_plus-0.0.16.gem"
)

$Missing = $Required | Where-Object { -not (Test-Path (Join-Path $Runtime $_)) }
if ($Missing) {
    $MissingText = $Missing -join [Environment]::NewLine
    throw "Windows release is missing required runtime files:`n$MissingText"
}
if (-not (Test-Path (Join-Path $Dist "$AppName\$AppName.exe"))) {
    throw "Windows release is missing the application executable."
}
& $Python (Join-Path $PSScriptRoot "audit_mathtype_runtime.py") `
    --runtime-root $Runtime `
    --ruby (Join-Path $Runtime "tools\ruby\bin\ruby.exe")
if ($LASTEXITCODE -ne 0) {
    throw "Windows MathType runtime audit failed."
}
Write-Host "Windows bundle audit passed." -ForegroundColor Green
