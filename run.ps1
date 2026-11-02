<#
.SYNOPSIS  Start the todo web GUI as a background service.
.EXAMPLE   ./run.ps1 -Port 8765 -Open
#>
param(
    [int]$Port = 8765,
    [string]$BindHost = "127.0.0.1",
    [string]$File = "",
    [switch]$Open
)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$pidFile = Join-Path $root ".todo-web.pid"
$log = Join-Path $root ".todo-web.log"

if (Test-Path $pidFile) {
    $old = [int](Get-Content $pidFile -Raw)
    if (Get-Process -Id $old -ErrorAction SilentlyContinue) {
        Write-Host "Already running (PID $old). Use ./stop.ps1 first."
        exit 0
    }
    Remove-Item $pidFile -Force
}

$python = (Get-Command python -ErrorAction SilentlyContinue)?.Source
if (-not $python) { $python = (Get-Command py -ErrorAction SilentlyContinue)?.Source }
if (-not $python) { Write-Error "Python not found on PATH."; exit 1 }

$argList = @("-m", "todo")
if ($File) { $argList += @("--file", $File) }
$argList += @("web", "--host", $BindHost, "--port", $Port)

$p = Start-Process -FilePath $python -ArgumentList $argList -WorkingDirectory $root `
    -WindowStyle Hidden -PassThru -RedirectStandardOutput $log -RedirectStandardError "$log.err"
Start-Sleep -Milliseconds 800
if ($p.HasExited) {
    Write-Error "Server exited immediately; see $log.err"
    exit 1
}
Set-Content -Path $pidFile -Value $p.Id
$url = "http://${BindHost}:$Port/"
Write-Host "todo web running at $url (PID $($p.Id))"
if ($Open) { Start-Process $url }
