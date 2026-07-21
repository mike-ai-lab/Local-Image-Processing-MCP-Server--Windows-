#Requires -Version 5.1
# Registers the tray app to start automatically at Windows login.
# Run this once. To undo, run remove_autostart.ps1

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonW    = Join-Path $ScriptDir ".venv\Scripts\pythonw.exe"
$TrayPy     = Join-Path $ScriptDir "tray.py"
$RegKey     = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$AppName    = "LocalImageAgent"

# pythonw.exe runs without a console window
$Command = "`"$PythonW`" `"$TrayPy`""

Set-ItemProperty -Path $RegKey -Name $AppName -Value $Command
Write-Host ""
Write-Host "  [OK] Auto-start registered." -ForegroundColor Green
Write-Host "       The tray icon will launch automatically at every login." -ForegroundColor Gray
Write-Host ""
Write-Host "  To remove auto-start, run: .\remove_autostart.ps1" -ForegroundColor DarkGray
Write-Host ""
