#Requires -Version 5.1
# ============================================================
# LocalImageAgent â€” Remote Update Script
# Run this on the second device to pull latest code and
# restart the server cleanly.
# ============================================================

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ScriptDir ".venv\Scripts\python.exe"
$TrayPy    = Join-Path $ScriptDir "tray.py"
$ServerPy  = Join-Path $ScriptDir "src\main_http.py"

Write-Host ""
Write-Host "  LocalImageAgent Update" -ForegroundColor Cyan
Write-Host "  ======================" -ForegroundColor Cyan
Write-Host ""

# ------------------------------------------------------------
# 1. Syntax-check current file before doing anything
# ------------------------------------------------------------
Write-Host "  [1/5] Checking current server syntax..." -ForegroundColor Gray
$check = & $PythonExe -m py_compile $ServerPy 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [WARN] Current main_http.py has a syntax error:" -ForegroundColor Yellow
    Write-Host "         $check" -ForegroundColor Yellow
    Write-Host "         Proceeding with pull â€” the update may fix it." -ForegroundColor Yellow
}

# ------------------------------------------------------------
# 2. Stop running server + ngrok gracefully
# ------------------------------------------------------------
Write-Host "  [2/5] Stopping running server..." -ForegroundColor Gray
Get-Process -Name "python", "pythonw" -ErrorAction SilentlyContinue |
    Where-Object { $_.MainModule.FileName -like "*LocalImageAgent*" } |
    Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process -Name "ngrok" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Write-Host "  Server stopped." -ForegroundColor Green

# ------------------------------------------------------------
# 3. Pull latest code from GitHub
# ------------------------------------------------------------
Write-Host "  [3/5] Pulling latest from GitHub..." -ForegroundColor Gray
$pull = git -C $ScriptDir pull origin main 2>&1
Write-Host "  $pull" -ForegroundColor Gray

if ($LASTEXITCODE -ne 0) {
    Write-Host "  [FAIL] git pull failed. Check your network or repo state." -ForegroundColor Red
    Write-Host "  $pull" -ForegroundColor Red
    exit 1
}
Write-Host "  Pull complete." -ForegroundColor Green

# ------------------------------------------------------------
# 4. Syntax-check the newly pulled file
# ------------------------------------------------------------
Write-Host "  [4/5] Verifying pulled server file..." -ForegroundColor Gray
$check = & $PythonExe -m py_compile $ServerPy 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [FAIL] Syntax error in pulled main_http.py:" -ForegroundColor Red
    Write-Host "         $check" -ForegroundColor Red
    Write-Host "  Checking for backup..." -ForegroundColor Yellow
    $backup = Join-Path $ScriptDir "src\main_http.py.backup"
    if (Test-Path $backup) {
        Copy-Item $backup $ServerPy -Force
        Write-Host "  Backup restored. Server will start from last known-good version." -ForegroundColor Yellow
    } else {
        Write-Host "  No backup found. Fix the code error before restarting." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "  Syntax OK." -ForegroundColor Green
}

# ------------------------------------------------------------
# 5. Restart tray (headless background service)
# ------------------------------------------------------------
Write-Host "  [5/5] Restarting LocalImageAgent service..." -ForegroundColor Gray
$pythonw = Join-Path $ScriptDir ".venv\Scripts\pythonw.exe"
Start-Process -FilePath $pythonw -ArgumentList "`"$TrayPy`"" -WindowStyle Hidden
Start-Sleep -Seconds 3

# Confirm port came up
$up = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 1
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect("127.0.0.1", 8765)
        $tcp.Close()
        $up = $true
        break
    } catch {}
}

Write-Host ""
if ($up) {
    Write-Host "  ============================================" -ForegroundColor White
    Write-Host "  Update complete. Server is RUNNING." -ForegroundColor Green
    Write-Host "  MCP URL: https://pectin-parting-caution.ngrok-free.dev/mcp" -ForegroundColor Yellow
    Write-Host "  ============================================" -ForegroundColor White
} else {
    Write-Host "  [FAIL] Server did not come up on port 8765 after restart." -ForegroundColor Red
    Write-Host "         Check agent.log for errors." -ForegroundColor Red
}
Write-Host ""
