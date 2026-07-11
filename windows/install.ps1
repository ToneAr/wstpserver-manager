<#
.SYNOPSIS
    Installs the Wolfram Kernel Pool (WSTPServer) as a Windows Scheduled Task
    that starts at logon and restarts automatically on failure.
#>
[CmdletBinding()]
param(
    [string]$WstpServerBin,
    [string]$KernelBin
)

$ErrorActionPreference = "Stop"

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigDir  = Join-Path $env:APPDATA "wolfram-pool"
$LogDir     = Join-Path $env:LOCALAPPDATA "wolfram-pool\logs"
$ConfigFile = Join-Path $ConfigDir "wstpserver.conf"
$LogFile    = Join-Path $LogDir "wstpserver.log"
$TaskName   = "WolframKernelPool"

function Find-FirstMatch {
    param([string[]]$Patterns)
    foreach ($pattern in $Patterns) {
        $match = Get-ChildItem -Path $pattern -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($match) { return $match.FullName }
    }
    return $null
}

# Walk up from a WolframKernel path looking for the sibling wstpserver.exe
# (the two are installed under the same product root, but the number of
# directory levels between them varies by version).
function Find-WstpServerFromKernel {
    param([string]$KernelPath)
    $dir = Split-Path -Parent $KernelPath
    for ($i = 0; $i -lt 4; $i++) {
        $candidate = Join-Path $dir "SystemFiles\Links\WSTPServer\wstpserver.exe"
        if (Test-Path $candidate) { return $candidate }
        $dir = Split-Path -Parent $dir
    }
    return $null
}

# wolframscript -showkernels is the primary detection method; fall back to
# scanning common install roots if wolframscript isn't on PATH.
if (-not $KernelBin) {
    $wolframscript = Get-Command wolframscript.exe -ErrorAction SilentlyContinue
    if ($wolframscript) {
        $lines = & $wolframscript.Source -showkernels 2>$null
        for ($i = 0; $i -lt $lines.Length; $i++) {
            if ($lines[$i] -match "best WolframKernel location") {
                $candidate = $lines[$i + 1].Trim()
                if ($candidate) { $KernelBin = $candidate; break }
            }
        }
    }
}
if (-not $KernelBin) {
    $KernelBin = Find-FirstMatch @(
        "$env:ProgramFiles\Wolfram Research\*\WolframKernel.exe"
        "${env:ProgramFiles(x86)}\Wolfram Research\*\WolframKernel.exe"
        "$env:ProgramFiles\Wolfram Research\*\wolfram.exe"
        "${env:ProgramFiles(x86)}\Wolfram Research\*\wolfram.exe"
    )
}

if (-not $WstpServerBin -and $KernelBin) {
    $WstpServerBin = Find-WstpServerFromKernel -KernelPath $KernelBin
}
if (-not $WstpServerBin) {
    $WstpServerBin = Find-FirstMatch @(
        "$env:ProgramFiles\Wolfram Research\*\SystemFiles\Links\WSTPServer\wstpserver.exe"
        "${env:ProgramFiles(x86)}\Wolfram Research\*\SystemFiles\Links\WSTPServer\wstpserver.exe"
    )
}

if (-not $KernelBin) {
    throw "Could not find the WolframKernel binary. Re-run with -KernelBin 'C:\path\to\WolframKernel.exe'."
}
if (-not $WstpServerBin) {
    throw "Could not find wstpserver.exe. Re-run with -WstpServerBin 'C:\path\to\wstpserver.exe'."
}

Write-Host "Using wstpserver: $WstpServerBin"
Write-Host "Using kernel:     $KernelBin"

New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if (Test-Path $ConfigFile) {
    Write-Host "Config already exists at $ConfigFile, leaving it untouched."
} else {
    $templatePath = Join-Path $ScriptDir "..\common\wstpserver.conf.json.template"
    $kernelPathJson = $KernelBin.Replace('\', '\\')
    (Get-Content $templatePath -Raw) -replace '__KERNEL_PATH__', $kernelPathJson |
        Set-Content -Path $ConfigFile -Encoding UTF8
    Write-Host "Wrote $ConfigFile"
}

$Action = New-ScheduledTaskAction -Execute $WstpServerBin `
    -Argument "-p 31415 -i localhost -c `"$ConfigFile`" -l 1 -f `"$LogFile`""

$Trigger = New-ScheduledTaskTrigger -AtLogOn

$Settings = New-ScheduledTaskSettingsSet `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask -TaskName $TaskName `
    -Action $Action -Trigger $Trigger -Settings $Settings `
    -Description "Wolfram Kernel Pool (WSTPServer)" | Out-Null

Start-ScheduledTask -TaskName $TaskName

Write-Host "Done. Check status with: Get-ScheduledTask -TaskName $TaskName"
