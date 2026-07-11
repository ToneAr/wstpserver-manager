<#
.SYNOPSIS
    Removes the Wolfram Kernel Pool (WSTPServer) scheduled task.
    Config and log files are left in place unless -Purge is passed.
#>
[CmdletBinding()]
param(
    [switch]$Purge
)

$ErrorActionPreference = "Stop"

$TaskName  = "WolframKernelPool"
$ConfigDir = Join-Path $env:APPDATA "wstpserver"
$LogDir    = Join-Path $env:LOCALAPPDATA "wstpserver\logs"
$RunKey    = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$RunValueName = "WSTPServer Manager"

Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Remove-ItemProperty -Path $RunKey -Name $RunValueName -ErrorAction SilentlyContinue

if ($Purge) {
    Remove-Item -Recurse -Force -Path $ConfigDir -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force -Path $LogDir -ErrorAction SilentlyContinue
    Write-Host "Removed task, config, and logs."
} else {
    Write-Host "Removed task. Config kept at $ConfigDir, logs kept at $LogDir."
}
