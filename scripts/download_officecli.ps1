$ErrorActionPreference = "Stop"

$Version = "1.0.142"
$Asset = "officecli-win-x64.exe"
$ExpectedSha256 = "676e0acee691288968a31b9832299ad05599e83140e801c382b6fc4509622fe2"
$Root = Split-Path -Parent $PSScriptRoot
$DestinationDirectory = Join-Path $Root "tools\officecli"
$Destination = Join-Path $DestinationDirectory $Asset
$DownloadUrl = "https://github.com/iOfficeAI/OfficeCLI/releases/download/v$Version/$Asset"

New-Item -ItemType Directory -Path $DestinationDirectory -Force | Out-Null

if (Test-Path $Destination) {
    $ExistingHash = (Get-FileHash -Algorithm SHA256 $Destination).Hash.ToLowerInvariant()
    if ($ExistingHash -eq $ExpectedSha256) {
        Write-Host "OfficeCLI $Version is already ready."
        exit 0
    }
}

$Temporary = "$Destination.download"
Invoke-WebRequest -Uri $DownloadUrl -OutFile $Temporary -UseBasicParsing
$ActualHash = (Get-FileHash -Algorithm SHA256 $Temporary).Hash.ToLowerInvariant()
if ($ActualHash -ne $ExpectedSha256) {
    Remove-Item $Temporary -Force
    throw "OfficeCLI checksum verification failed."
}

Move-Item $Temporary $Destination -Force
Write-Host "OfficeCLI $Version downloaded and verified: $Destination"
