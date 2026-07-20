#Requires -Version 5.1
# Launcher for LocalImageAgent MCP Server
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ScriptDir ".venv\Scripts\python.exe"
$MainPy    = Join-Path $ScriptDir "src\main.py"
& $PythonExe $MainPy
