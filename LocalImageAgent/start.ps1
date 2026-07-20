#Requires -Version 5.1
# One-click launcher: starts the MCP HTTP server + ngrok tunnel

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe  = Join-Path $ScriptDir ".venv\Scripts\python.exe"
$MainHttp   = Join-Path $ScriptDir "src\main_http.py"
$NgrokExe   = Join-Path $ScriptDir "ngrok\ngrok.exe"
$ServerLog  = Join-Path $ScriptDir "server.log"
$ServerErr  = Join-Path $ScriptDir "server_err.log"
$StaticUrl  = "https://pectin-parting-caution.ngrok-free.dev"
$McpPath    = "/mcp"

Write-Host ""
Write-Host "  Starting LocalImageAgent..." -ForegroundColor Cyan

# Kill any process holding port 8765 from a previous run
$netOut = netstat -ano 2>$null
$netOut | Select-String ":8765 " | ForEach-Object {
    $parts = ($_ -split "\s+")
    $procId = $parts[-1]
    if ($procId -match "^\d+$" -and [int]$procId -ne 0) {
        Stop-Process -Id ([int]$procId) -Force -ErrorAction SilentlyContinue
    }
}
Get-Process -Name "ngrok" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

# ---------------------------------------------------------------------------
# 1. Start MCP server
# ---------------------------------------------------------------------------
$server = Start-Process -FilePath $PythonExe -ArgumentList "`"$MainHttp`"" `
    -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput $ServerLog `
    -RedirectStandardError $ServerErr
Write-Host "  MCP server started (PID $($server.Id))" -ForegroundColor Green

# Wait until port 8765 is listening (up to 15 seconds)
$listening = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 1
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect("127.0.0.1", 8765)
        $tcp.Close()
        $listening = $true
        break
    } catch {}
}

if (-not $listening) {
    Write-Host "  [FAIL] MCP server did not start. Last error:" -ForegroundColor Red
    Get-Content $ServerErr -ErrorAction SilentlyContinue | Select-Object -Last 20
    exit 1
}
Write-Host "  MCP server is listening on port 8765" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 2. Start ngrok with permanent static domain
# ---------------------------------------------------------------------------
$ngrokArgs = "http 8765 --domain=$StaticUrl".Replace("https://","")
$ngrok = Start-Process -FilePath $NgrokExe -ArgumentList $ngrokArgs `
    -PassThru -WindowStyle Hidden
Write-Host "  ngrok tunnel started (PID $($ngrok.Id))" -ForegroundColor Green
Start-Sleep -Seconds 2

# ---------------------------------------------------------------------------
# 3. Print permanent URL
# ---------------------------------------------------------------------------
$fullUrl = $StaticUrl + $McpPath
Write-Host ""
Write-Host "  ============================================" -ForegroundColor White
Write-Host "  ChatGPT MCP Server URL (permanent):"        -ForegroundColor White
Write-Host "  $fullUrl"                                    -ForegroundColor Yellow
Write-Host "  ============================================" -ForegroundColor White
Write-Host ""
Write-Host "  This URL never changes." -ForegroundColor Gray
Write-Host "  Press Ctrl+C to stop."   -ForegroundColor DarkGray
Write-Host ""
[System.Windows.Forms.Clipboard]::SetText($fullUrl) 2>$null
Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
[System.Windows.Forms.Clipboard]::SetText($fullUrl) 2>$null
Write-Host "  (copied to clipboard)"   -ForegroundColor DarkGray
Write-Host ""

# ---------------------------------------------------------------------------
# 4. Keep alive
# ---------------------------------------------------------------------------
try {
    while ($true) {
        Start-Sleep -Seconds 5
        if ($server.HasExited) {
            Write-Host "  [WARN] MCP server stopped. Check server_err.log" -ForegroundColor Yellow
            break
        }
        if ($ngrok.HasExited) {
            Write-Host "  [WARN] ngrok stopped unexpectedly." -ForegroundColor Yellow
            break
        }
    }
} finally {
    Write-Host "  Stopping..." -ForegroundColor DarkGray
    Stop-Process -Id $server.Id -ErrorAction SilentlyContinue
    Stop-Process -Id $ngrok.Id  -ErrorAction SilentlyContinue
}
