#Requires -Version 5.1
# HTTP/SSE launcher for LocalImageAgent — use this for ChatGPT Desktop
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ScriptDir ".venv\Scripts\python.exe"
$MainPy    = Join-Path $ScriptDir "src\main_http.py"

Write-Host ""
Write-Host "  LocalImageAgent HTTP Server" -ForegroundColor Cyan
Write-Host "  MCP URL for ChatGPT Desktop: http://127.0.0.1:8765/sse" -ForegroundColor Green
Write-Host "  Press Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

& $PythonExe `"$MainPy`"
