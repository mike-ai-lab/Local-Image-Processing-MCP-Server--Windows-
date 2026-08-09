#Requires -Version 5.1
Set-StrictMode -Off
$ErrorActionPreference = "Continue"

$ScriptDir      = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir        = Join-Path $ScriptDir ".venv"
$ConfigFile     = Join-Path $ScriptDir "config.json"
$TrayScript     = Join-Path $ScriptDir "tray.py"
$NgrokDir       = Join-Path $ScriptDir "ngrok"
$NgrokAuthToken = "3Gk8t1O4bcaHODsS4z7GK2jv2o2_22KQpqahcmZbwWcZbjAjb"
$NgrokDomain    = "pectin-parting-caution.ngrok-free.dev"

function Write-Step([string]$msg) { Write-Host ""; Write-Host "  ==> $msg" -ForegroundColor Cyan }
function Write-OK([string]$msg)   { Write-Host "      [OK] $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "      [WARN] $msg" -ForegroundColor Yellow }
function Write-Fail([string]$msg) { Write-Host "      [FAIL] $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "  ================================================" -ForegroundColor White
Write-Host "   LocalImageAgent MCP Server - Setup" -ForegroundColor White
Write-Host "  ================================================" -ForegroundColor White

# 1. Python
Write-Step "Checking Python..."
$pythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            if ([int]$Matches[1] -ge 3 -and [int]$Matches[2] -ge 10) {
                $pythonCmd = $cmd
                Write-OK "Found $ver"
                break
            }
        }
    } catch {}
}
if (-not $pythonCmd) {
    Write-Fail "Python 3.10+ not found. Download from https://www.python.org/downloads/"
    exit 1
}

# 2. Virtual environment
Write-Step "Setting up virtual environment..."
if (-not (Test-Path $VenvDir)) {
    & $pythonCmd -m venv $VenvDir
    Write-OK "Created .venv"
} else {
    Write-OK ".venv already exists"
}
$PipExe    = Join-Path $VenvDir "Scripts\pip.exe"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$PythonW   = Join-Path $VenvDir "Scripts\pythonw.exe"

# 3. Python dependencies
Write-Step "Installing Python dependencies..."
& $PipExe install --upgrade pip --quiet 2>$null
& $PipExe install -r (Join-Path $ScriptDir "requirements.txt")
Write-OK "Dependencies installed"

# 4. ImageMagick
Write-Step "Checking ImageMagick..."
$magickExe = $null
$found = Get-Command "magick.exe" -ErrorAction SilentlyContinue
if ($found) { $magickExe = $found.Source }
if (-not $magickExe) {
    $hits = Get-Item "C:\Program Files\ImageMagick-7*\magick.exe" -ErrorAction SilentlyContinue | Sort-Object Name -Descending
    if ($hits) { $magickExe = $hits[0].FullName }
}
if ($magickExe) {
    Write-OK "Found: $magickExe"
} else {
    Write-Warn "ImageMagick not found. Download from https://imagemagick.org/script/download.php#windows"
}

# 5. FFmpeg
Write-Step "Checking FFmpeg..."
$ffmpegExe = $null
$ffFound = Get-Command "ffmpeg.exe" -ErrorAction SilentlyContinue
if ($ffFound) { $ffmpegExe = $ffFound.Source }
if (-not $ffmpegExe) {
    $hits = Get-Item "C:\ffmpeg\bin\ffmpeg.exe" -ErrorAction SilentlyContinue
    if ($hits) { $ffmpegExe = $hits.FullName }
}
if ($ffmpegExe) {
    Write-OK "Found: $ffmpegExe"
} else {
    Write-Warn "FFmpeg not found. Download from https://ffmpeg.org/download.html"
}

# 6. ngrok
Write-Step "Checking ngrok..."
$ngrokExe = Join-Path $NgrokDir "ngrok.exe"
if (-not (Test-Path $ngrokExe)) {
    Write-Warn "ngrok.exe not found at $ngrokExe"
    Write-Warn "Place ngrok.exe in the ngrok\ subfolder, then re-run setup."
} else {
    & $ngrokExe config add-authtoken $NgrokAuthToken 2>$null | Out-Null
    Write-OK "ngrok configured"
}

# 7. Write config.json
Write-Step "Writing config.json..."
$magickDir = if ($magickExe) { Split-Path -Parent $magickExe } else { "" }
$configObj = [ordered]@{
    imagemagick_path         = $magickDir
    magick_exe               = if ($magickExe) { $magickExe } else { "magick" }
    ffmpeg_exe               = if ($ffmpegExe) { $ffmpegExe } else { "ffmpeg" }
    server_name              = "local-image-agent"
    server_version           = "1.0.0"
    log_level                = "INFO"
    supported_input_formats  = @("jpg","jpeg","png","tiff","bmp","gif","webp","avif")
    supported_output_formats = @("jpg","png","tiff","bmp","webp","avif")
}
$json = $configObj | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText($ConfigFile, $json, [System.Text.UTF8Encoding]::new($false))
Write-OK "config.json written"

# 8. Register auto-start on Windows login
Write-Step "Registering auto-start on login..."
$regKey  = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$regName = "LocalImageAgentMCP"
$startCmd = "`"$PythonW`" `"$TrayScript`""
Set-ItemProperty -Path $regKey -Name $regName -Value $startCmd -Force -ErrorAction SilentlyContinue
Write-OK "Registered for auto-start"

# 9. Summary
Write-Host ""
Write-Host "  ================================================" -ForegroundColor Green
Write-Host "   Setup complete!" -ForegroundColor Green
Write-Host "  ================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  ChatGPT MCP URL: https://$NgrokDomain/mcp" -ForegroundColor Yellow
Write-Host "  To start: .\start.ps1" -ForegroundColor White
Write-Host ""

# 10. Launch now
$launch = Read-Host "  Launch the MCP server now? (Y/n)"
if ($launch -ne 'n' -and $launch -ne 'N') {
    Stop-Process -Name "python","pythonw","ngrok" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    Start-Process -FilePath $PythonW -ArgumentList "`"$TrayScript`"" -WindowStyle Hidden
    Write-Host "  Server starting. Check agent.log for status." -ForegroundColor Green
}
Write-Host ""
