[CmdletBinding()]
param(
    [string]$DistDir,
    [string]$Version
)

$ErrorActionPreference = "Stop"
$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
Push-Location $RootDir
try {
if (-not $DistDir) {
    $DistDir = Join-Path $RootDir "dist\WSTPServerManager"
}

if (-not $Version) {
    $Version = python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])"
}

$exe = Join-Path $DistDir "WSTPServerManager.exe"
if (-not (Test-Path $exe)) {
    throw "Expected PyInstaller bundle at $DistDir. Build it first with: python -m PyInstaller --noconfirm packaging/pyinstaller/wstpserver-tray.spec"
}

$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
    $iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
}
if (-not $iscc) {
    throw "Inno Setup compiler (ISCC.exe) was not found. Install Inno Setup, then re-run this script."
}

$script = Join-Path (Get-Location) "packaging\installers\windows\WSTPServerManager.iss"
& $iscc.Source "/DAppVersion=$Version" "/DDistDir=$DistDir" $script
} finally {
    Pop-Location
}
