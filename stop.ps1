<#
.SYNOPSIS  Stop the todo web GUI started by run.ps1.
#>
$pidFile = Join-Path $PSScriptRoot ".todo-web.pid"
if (-not (Test-Path $pidFile)) { Write-Host "Not running (no PID file)."; exit 0 }
$id = [int](Get-Content $pidFile -Raw)
if (Get-Process -Id $id -ErrorAction SilentlyContinue) {
    Stop-Process -Id $id -Force
    Write-Host "Stopped todo web (PID $id)."
} else {
    Write-Host "Process $id was not running."
}
Remove-Item $pidFile -Force
