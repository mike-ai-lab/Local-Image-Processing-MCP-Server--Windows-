#Requires -Version 5.1
<#
.SYNOPSIS
    Full one-command setup for LocalImageAgent MCP Server on any Windows machine.
.DESCRIPTION
    - Checks Python 3.10+ (prompts to install if missing)
    - Creates .venv and installs all Python dependencies
    - Downloads and installs ImageMagick if not found
    - Downloads and installs FFmpeg if not found
    - Downloads ngrok if not found
    - Writes config.json
    - Registers tray app as Windows startup item
    - Creates desktop shortcut
    - Starts the tray app
#>

Set-StrictMode -Off
$ErrorActionPreference = "Continue"

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir    = Join-Path $ScriptDir ".venv"
$SrcDir     = Join-Path $ScriptDir "src"
$NgrokDir   = Join-Path $ScriptDir "ngrok"
$ConfigFile = Join-Path $ScriptDir "config.json"
$TrayScript = Join-Path $ScriptDir "tray.py"

# Ngrok auth token — update this if you need a different account
$NgrokAuthToken = "3Gk8t1O4bcaHODsS4z7GK2jv2o2_22KQpqahcmZbwWcZbjAjb"
$NgrokDomain    = "pectin-parting-caution.ngrok-free.dev"

function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host "  ==> $msg" -ForegroundColor Cyan
}
function Write-OK([string]$msg)   { Write-Host "      [OK] $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "      [WARN] $msg" -ForegroundColor Yellow }
function Write-Fail([string]$msg) { Write-Host "      [FAIL] $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "  ================================================" -ForegroundColor White
Write-Host "   LocalImageAgent MCP Server - Setup" -ForegroundColor White
Write-Host "  ================================================" -ForegroundColor White

# ---------------------------------------------------------------------------
# 1. Python
# ---------------------------------------------------------------------------
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
    Write-Fail "Python 3.10+ not found."
    Write-Host "      Download from: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "      Install with 'Add Python to PATH' checked, then re-run setup.ps1" -ForegroundColor Yellow
    Read-Host "      Press Enter to open the Python download page..."
    Start-Process "https://www.python.org/downloads/"
    exit 1
}

$PythonExe = $null

# ---------------------------------------------------------------------------
# 2. Virtual environment
# ---------------------------------------------------------------------------
Write-Step "Setting up virtual environment..."

if (-not (Test-Path $VenvDir)) {
    & $pythonCmd -m venv $VenvDir
    Write-OK "Created .venv"
} else {
    Write-OK ".venv already exists"
}

$PipExe    = Join-Path $VenvDir "Scripts\pip.exe"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

# ---------------------------------------------------------------------------
# 3. Python dependencies
# ---------------------------------------------------------------------------
Write-Step "Installing Python dependencies..."

& $PipExe install --upgrade pip --quiet 2>$null
& $PipExe install -r (Join-Path $ScriptDir "requirements.txt") --quiet
if ($LASTEXITCODE -ne 0) {
    # Try without --quiet for visibility
    & $PipExe install -r (Join-Path $ScriptDir "requirements.txt")
}
# pystray for tray app
& $PipExe install pystray --quiet 2>$null
Write-OK "Dependencies installed"

# ---------------------------------------------------------------------------
# 4. ImageMagick
# ---------------------------------------------------------------------------
Write-Step "Checking ImageMagick..."

$magickExe = $null
$found = Get-Command "magick.exe" -ErrorAction SilentlyContinue
if ($found) { $magickExe = $found.Source }

if (-not $magickExe) {
    $candidates = @(
        "C:\Program Files\ImageMagick-7*\magick.exe",
        "C:\Program Files (x86)\ImageMagick-7*\magick.exe",
        "C:\Program Files\ImageMagick-6*\magick.exe"
    )
    foreach ($p in $candidates) {
        $hits = Get-Item $p -ErrorAction SilentlyContinue | Sort-Object Name -Descending
        if ($hits) { $magickExe = $hits[0].FullName; break }
    }
}

if ($magickExe) {
    Write-OK "Found: $magickExe"
} else {
    Write-Warn "ImageMagick not found — downloading installer..."
    $imUrl      = "https://imagemagick.org/archive/binaries/ImageMagick-7.1.1-47-Q16-HDRI-x64-dll.exe"
    $imInstaller = Join-Path $env:TEMP "ImageMagick-setup.exe"
    try {
        Invoke-WebRequest -Uri $imUrl -OutFile $imInstaller -UseBasicParsing
        Write-OK "Downloaded ImageMagick installer"
        Write-Host "      Running installer (follow the prompts — check 'Add to PATH')..." -ForegroundColor Yellow
        Start-Process -FilePath $imInstaller -ArgumentList "/SILENT", "/TASKS=modifypath" -Wait
        # Re-check after install
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH", "User")
        $found2 = Get-Command "magick.exe" -ErrorAction SilentlyContinue
        if ($found2) {
            $magickExe = $found2.Source
            Write-OK "ImageMagick installed: $magickExe"
        } else {
            # Try common post-install path
            $hits = Get-Item "C:\Program Files\ImageMagick-7*\magick.exe" -ErrorAction SilentlyContinue | Sort-Object Name -Descending
            if ($hits) { $magickExe = $hits[0].FullName; Write-OK "Found at: $magickExe" }
            else { Write-Warn "ImageMagick installed but path not found — you may need to restart and re-run" }
        }
    } catch {
        Write-Warn "Could not download ImageMagick: $_"
        Write-Host "      Install manually from https://imagemagick.org/script/download.php#windows" -ForegroundColor Yellow
    }
}

# ---------------------------------------------------------------------------
# 5. FFmpeg
# ---------------------------------------------------------------------------
Write-Step "Checking FFmpeg..."

$ffmpegExe = $null
$ffFound = Get-Command "ffmpeg.exe" -ErrorAction SilentlyContinue
if ($ffFound) { $ffmpegExe = $ffFound.Source }

if (-not $ffmpegExe) {
    $ffCandidates = @(
        "C:\ffmpeg\bin\ffmpeg.exe",
        "C:\ffmpeg\ffmpeg-*\bin\ffmpeg.exe",
        "C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        "C:\Tools\ffmpeg\bin\ffmpeg.exe"
    )
    foreach ($p in $ffCandidates) {
        $hits = Get-Item $p -ErrorAction SilentlyContinue | Sort-Object Name -Descending
        if ($hits) { $ffmpegExe = $hits[0].FullName; break }
    }
}

if ($ffmpegExe) {
    Write-OK "Found: $ffmpegExe"
} else {
    Write-Warn "FFmpeg not found — downloading..."
    $ffUrl  = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    $ffZip  = Join-Path $env:TEMP "ffmpeg.zip"
    $ffDest = "C:\ffmpeg"
    try {
        Invoke-WebRequest -Uri $ffUrl -OutFile $ffZip -UseBasicParsing
        Write-OK "Downloaded FFmpeg"
        Expand-Archive -Path $ffZip -DestinationPath $ffDest -Force
        # Find the bin directory
        $ffBin = Get-ChildItem "$ffDest\ffmpeg-*\bin\ffmpeg.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($ffBin) {
            $ffmpegExe = $ffBin.FullName
            # Add to system PATH
            $binDir = Split-Path $ffmpegExe
            $sysPath = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
            if ($sysPath -notlike "*$binDir*") {
                [System.Environment]::SetEnvironmentVariable("PATH", "$sysPath;$binDir", "Machine")
            }
            Write-OK "FFmpeg installed: $ffmpegExe"
        }
        Remove-Item $ffZip -Force -ErrorAction SilentlyContinue
    } catch {
        Write-Warn "Could not download FFmpeg: $_"
        Write-Host "      Install manually from https://ffmpeg.org/download.html" -ForegroundColor Yellow
    }
}

# ---------------------------------------------------------------------------
# 6. ngrok
# ---------------------------------------------------------------------------
Write-Step "Checking ngrok..."

$ngrokExe = Join-Path $NgrokDir "ngrok.exe"
if (-not (Test-Path $ngrokExe)) {
    Write-Warn "ngrok not found — downloading..."
    $ngrokUrl = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip"
    $ngrokZip = Join-Path $env:TEMP "ngrok.zip"
    try {
        New-Item -ItemType Directory -Path $NgrokDir -Force | Out-Null
        Invoke-WebRequest -Uri $ngrokUrl -OutFile $ngrokZip -UseBasicParsing
        Expand-Archive -Path $ngrokZip -DestinationPath $NgrokDir -Force
        Remove-Item $ngrokZip -Force -ErrorAction SilentlyContinue
        Write-OK "ngrok downloaded"
    } catch {
        Write-Warn "Could not download ngrok: $_"
    }
}

if (Test-Path $ngrokExe) {
    # Configure auth token
    & $ngrokExe config add-authtoken $NgrokAuthToken 2>$null | Out-Null
    Write-OK "ngrok configured with auth token"
} else {
    Write-Warn "ngrok.exe not found at $ngrokExe"
}

# ---------------------------------------------------------------------------
# 7. Write config.json
# ---------------------------------------------------------------------------
Write-Step "Writing config.json..."

$magickDir = if ($magickExe -and $magickExe -ne "magick") { Split-Path -Parent $magickExe } else { "" }
$ffDir     = if ($ffmpegExe) { Split-Path -Parent $ffmpegExe } else { "" }

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

# ---------------------------------------------------------------------------
# 8. Register tray app as Windows startup item
# ---------------------------------------------------------------------------
Write-Step "Registering tray app for auto-start on login..."

$regKey  = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$regName = "LocalImageAgentMCP"
$startCmd = "`"$($PythonExe -replace '\\','/')`" `"$($TrayScript -replace '\\','/')`""

Set-ItemProperty -Path $regKey -Name $regName -Value $startCmd -Force -ErrorAction SilentlyContinue
Write-OK "Registered: will auto-start on Windows login"

# ---------------------------------------------------------------------------
# 9. Create desktop shortcut
# ---------------------------------------------------------------------------
Write-Step "Creating desktop shortcut..."

$desktopPath   = [Environment]::GetFolderPath("Desktop")
$shortcutPath  = Join-Path $desktopPath "Image MCP Server.lnk"

try {
    $wsh     = New-Object -ComObject WScript.Shell
    $shortcut = $wsh.CreateShortcut($shortcutPath)
    $shortcut.TargetPath    = $PythonExe
    $shortcut.Arguments     = "`"$TrayScript`""
    $shortcut.WorkingDirectory = $ScriptDir
    $shortcut.Description   = "Start LocalImageAgent MCP Server tray app"
    $shortcut.WindowStyle   = 7  # minimized
    $shortcut.Save()
    Write-OK "Desktop shortcut created: $shortcutPath"
} catch {
    Write-Warn "Could not create desktop shortcut: $_"
}

# ---------------------------------------------------------------------------
# 10. Summary
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "  ================================================" -ForegroundColor Green
Write-Host "   Setup complete!" -ForegroundColor Green
Write-Host "  ================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  ImageMagick : $(if ($magickExe) { $magickExe } else { 'NOT FOUND - install manually' })" -ForegroundColor $(if ($magickExe) { 'White' } else { 'Yellow' })
Write-Host "  FFmpeg      : $(if ($ffmpegExe) { $ffmpegExe } else { 'NOT FOUND - install manually' })" -ForegroundColor $(if ($ffmpegExe) { 'White' } else { 'Yellow' })
Write-Host "  ngrok       : $(if (Test-Path $ngrokExe) { $ngrokExe } else { 'NOT FOUND' })" -ForegroundColor $(if (Test-Path $ngrokExe) { 'White' } else { 'Yellow' })
Write-Host ""
Write-Host "  ChatGPT MCP URL (permanent):" -ForegroundColor White
Write-Host "  https://$NgrokDomain/mcp" -ForegroundColor Yellow
Write-Host ""
Write-Host "  To start the server:" -ForegroundColor White
Write-Host "    Double-click 'Image MCP Server' on your desktop" -ForegroundColor Gray
Write-Host "    OR run: .\start.ps1" -ForegroundColor Gray
Write-Host ""
Write-Host "  The tray app will auto-start on every Windows login." -ForegroundColor Gray
Write-Host ""

# ---------------------------------------------------------------------------
# 11. Launch tray now
# ---------------------------------------------------------------------------
$launch = Read-Host "  Launch the MCP server now? (Y/n)"
if ($launch -ne 'n' -and $launch -ne 'N') {
    Write-Host "  Starting tray app..." -ForegroundColor Cyan
    Start-Process -FilePath $PythonExe -ArgumentList "`"$TrayScript`"" -WindowStyle Hidden
    Write-Host "  Tray icon should appear in the system tray shortly." -ForegroundColor Green
}

Write-Host ""
