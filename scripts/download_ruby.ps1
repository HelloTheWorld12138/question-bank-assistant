$ErrorActionPreference = "Stop"

# The MathType converter is a local Ruby program.  Bundle a private Ruby
# runtime so teachers do not have to install Ruby or modify PATH themselves.
$Version = "3.3.7-1"
$NokogiriVersion = "1.18.10"
$NokogiriAsset = "nokogiri-$NokogiriVersion-x64-mingw-ucrt.gem"
$NokogiriSha256 = "64f40d4a41af9f7f83a4e236ad0cf8cca621b97e31f727b1bebdae565a653104"
$Asset = "rubyinstaller-$Version-x64.exe"
$Root = Split-Path -Parent $PSScriptRoot
$DestinationDirectory = Join-Path $Root "tools\ruby"
$Ruby = Join-Path $DestinationDirectory "bin\ruby.exe"
$DownloadUrl = "https://github.com/oneclick/rubyinstaller2/releases/download/RubyInstaller-$Version/$Asset"

if (-not (Test-Path $Ruby)) {
    $TemporaryDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ("rubyinstaller-" + [guid]::NewGuid())
    $Installer = Join-Path $TemporaryDirectory $Asset
    New-Item -ItemType Directory -Path $TemporaryDirectory -Force | Out-Null

    try {
        Invoke-WebRequest -Uri $DownloadUrl -OutFile $Installer -UseBasicParsing
        New-Item -ItemType Directory -Path $DestinationDirectory -Force | Out-Null
        $process = Start-Process -FilePath $Installer -ArgumentList @(
            "/verysilent",
            "/suppressmsgboxes",
            "/norestart",
            "/dir=`"$DestinationDirectory`""
        ) -Wait -PassThru
        if ($process.ExitCode -ne 0 -or -not (Test-Path $Ruby)) {
            throw "Ruby runtime installation failed."
        }
        # This is an application-private runtime, not a separately uninstallable app.
        Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $DestinationDirectory "unins000.exe"), (Join-Path $DestinationDirectory "unins000.dat")
    }
    finally {
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $TemporaryDirectory
    }
}

& $Ruby -e "begin; require 'nokogiri'; exit(Nokogiri::VERSION == '$NokogiriVersion' ? 0 : 1); rescue LoadError; exit 1; end"
if ($LASTEXITCODE -ne 0) {
    $NokogiriTemporaryDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ("nokogiri-" + [guid]::NewGuid())
    $NokogiriGem = Join-Path $NokogiriTemporaryDirectory $NokogiriAsset
    New-Item -ItemType Directory -Path $NokogiriTemporaryDirectory -Force | Out-Null
    try {
        Invoke-WebRequest `
            -Uri "https://rubygems.org/downloads/$NokogiriAsset" `
            -OutFile $NokogiriGem `
            -UseBasicParsing
        $ActualNokogiriSha256 = (Get-FileHash -Algorithm SHA256 $NokogiriGem).Hash.ToLowerInvariant()
        if ($ActualNokogiriSha256 -ne $NokogiriSha256) {
            throw "Nokogiri checksum verification failed."
        }
        & $Ruby -S gem install $NokogiriGem --local --no-document
        if ($LASTEXITCODE -ne 0) {
            throw "Nokogiri runtime installation failed."
        }
    }
    finally {
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $NokogiriTemporaryDirectory
    }
}
& $Ruby -e "require 'nokogiri'; abort 'Unexpected Nokogiri version' unless Nokogiri::VERSION == '$NokogiriVersion'"
if ($LASTEXITCODE -ne 0) {
    throw "Nokogiri runtime verification failed."
}

Write-Host "Ruby $Version and Nokogiri $NokogiriVersion are ready: $Ruby"
