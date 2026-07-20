#Requires -Version 5.1
# Creates a desktop shortcut that launches the tray app

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ScriptDir ".venv\Scripts\pythonw.exe"  # pythonw = no console window
$TrayPy    = Join-Path $ScriptDir "tray.py"
$Desktop   = [Environment]::GetFolderPath("Desktop")
$Shortcut  = Join-Path $Desktop "Image MCP Server.lnk"

$Wsh  = New-Object -ComObject WScript.Shell
$Link = $Wsh.CreateShortcut($Shortcut)
$Link.TargetPath       = $PythonExe
$Link.Arguments        = "`"$TrayPy`""
$Link.WorkingDirectory = $ScriptDir
$Link.Description      = "Start LocalImageAgent MCP Server"
$Link.Save()

Write-Host "Shortcut created on Desktop: 'Image MCP Server'" -ForegroundColor Green
Write-Host "Double-click it to start the server tray icon." -ForegroundColor Cyan
