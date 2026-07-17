$ErrorActionPreference = "Stop"

param(
  [Parameter(Mandatory = $true)]
  [string]$RepositoryUrl
)

if ($RepositoryUrl -match "HelloTheWorld12138/computational-physics") {
  throw "Refusing to publish to computational-physics. This project must use a separate repository."
}

if ($RepositoryUrl -notmatch "^https://github\.com/[^/]+/[^/]+(\.git)?$") {
  throw "RepositoryUrl must look like https://github.com/<user>/<repo>.git"
}

$LocalGit = Join-Path $PSScriptRoot "tools\git\cmd\git.exe"
$Git = $null
if (Test-Path $LocalGit) {
  $Git = $LocalGit
} else {
  $GitCommand = Get-Command "git" -ErrorAction SilentlyContinue
  if ($GitCommand) {
    $Git = $GitCommand.Source
  }
}
if (-not $Git) {
  throw "Git was not found. Install Git for Windows first: https://git-scm.com/download/win"
}

$Root = Resolve-Path (Join-Path $PSScriptRoot ".")
Set-Location $Root

if (-not (Test-Path ".git")) {
  & $Git init
  & $Git branch -M main
}

$ExistingOrigin = & $Git remote get-url origin 2>$null
if ($LASTEXITCODE -eq 0 -and $ExistingOrigin) {
  if ($ExistingOrigin -match "HelloTheWorld12138/computational-physics") {
    & $Git remote remove origin
  } else {
    Write-Host "Existing origin: $ExistingOrigin"
    & $Git remote remove origin
  }
}

& $Git remote add origin $RepositoryUrl
& $Git add -A
& $Git commit -m "高中物理题库助手 MVP"
& $Git branch -M main
& $Git push -u origin main

Write-Host ""
Write-Host "Published to $RepositoryUrl"
