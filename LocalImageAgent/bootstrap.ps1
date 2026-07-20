#Requires -Version 5.1
<#
.SYNOPSIS
    Bootstrap script for LocalImageAgent MCP Server.
.DESCRIPTION
    Creates virtual environment, installs dependencies, detects ImageMagick,
    generates config.json, creates a launcher, and starts the MCP server.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir     = Join-Path $ScriptDir ".venv"
$SrcDir      = Join-Path $ScriptDir "src"
$ConfigFile  = Join-Path $ScriptDir "config.json"
$LauncherFile = Join-Path $ScriptDir "run_server.ps1"
$Req         = Join-Path $ScriptDir "requirements.txt"

function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Write-OK([string]$msg) {
    Write-Host "    [OK] $msg" -ForegroundColor Green
}

function Write-Fail([string]$msg) {
    Write-Host "    [FAIL] $msg" -ForegroundColor Red
}

# ---------------------------------------------------------------------------
# 1. Verify Python 3.12+
# ---------------------------------------------------------------------------
Write-Step "Checking Python..."

$pythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 12) {
                $pythonCmd = $cmd
                Write-OK "Found $ver ($cmd)"
                break
            }
        }
    } catch { }
}

if (-not $pythonCmd) {
    Write-Fail "Python 3.12+ not found. Please install from https://www.python.org/downloads/"
    exit 1
}

# ---------------------------------------------------------------------------
# 2. Create virtual environment
# ---------------------------------------------------------------------------
Write-Step "Setting up virtual environment..."

if (-not (Test-Path $VenvDir)) {
    & $pythonCmd -m venv $VenvDir
    Write-OK "Created .venv"
} else {
    Write-OK ".venv already exists, skipping creation"
}

$PipExe    = Join-Path $VenvDir "Scripts\pip.exe"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

# ---------------------------------------------------------------------------
# 3. Install dependencies
# ---------------------------------------------------------------------------
Write-Step "Installing requirements..."
& $PipExe install --upgrade pip --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "    [WARN] pip upgrade failed (exit $LASTEXITCODE), continuing..." -ForegroundColor Yellow
}
& $PipExe install -r $Req
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Dependency installation failed (exit $LASTEXITCODE). Check disk space and network, then re-run bootstrap.ps1."
    exit 1
}
Write-OK "Dependencies installed"

# ---------------------------------------------------------------------------
# 4. Detect ImageMagick
# ---------------------------------------------------------------------------
Write-Step "Detecting ImageMagick..."

$magickExe = $null

# Search PATH
$found = Get-Command "magick.exe" -ErrorAction SilentlyContinue
if ($found) {
    $magickExe = $found.Source
    Write-OK "Found via PATH: $magickExe"
}

# Common install locations
if (-not $magickExe) {
    $candidates = @(
        "C:\Program Files\ImageMagick-7*\magick.exe",
        "C:\Program Files (x86)\ImageMagick-7*\magick.exe",
        "C:\Program Files\ImageMagick-6*\magick.exe",
        "C:\Tools\ImageMagick\magick.exe"
    )
    foreach ($pattern in $candidates) {
        $hits = Get-Item $pattern -ErrorAction SilentlyContinue | Sort-Object Name -Descending
        if ($hits) {
            $magickExe = $hits[0].FullName
            Write-OK "Found at: $magickExe"
            break
        }
    }
}

if (-not $magickExe) {
    Write-Host ""
    Write-Host "    [WARN] ImageMagick not found. Download from https://imagemagick.org/script/download.php#windows" -ForegroundColor Yellow
    Write-Host "           After installing, re-run bootstrap.ps1 or manually set 'magick_exe' in config.json." -ForegroundColor Yellow
    $magickExe = "magick"  # fallback — will fail at runtime if not on PATH
}

# ---------------------------------------------------------------------------
# 5. Write config.json
# ---------------------------------------------------------------------------
Write-Step "Writing config.json..."

$magickDir = if ($magickExe -ne "magick") { Split-Path -Parent $magickExe } else { "" }

$configObj = [ordered]@{
    imagemagick_path         = $magickDir
    magick_exe               = $magickExe
    server_name              = "local-image-agent"
    server_version           = "1.0.0"
    log_level                = "INFO"
    supported_input_formats  = @("jpg","jpeg","png","tiff","bmp","gif","webp","avif")
    supported_output_formats = @("jpg","png","tiff","bmp","webp","avif")
}

$configObj | ConvertTo-Json -Depth 5 | ForEach-Object { [System.IO.File]::WriteAllText($ConfigFile, $_, [System.Text.UTF8Encoding]::new($false)) }
Write-OK "config.json written"

# ---------------------------------------------------------------------------
# 6. Create launcher script
# ---------------------------------------------------------------------------
Write-Step "Creating launcher (run_server.ps1)..."

$launcherContent = @"
#Requires -Version 5.1
# Launcher for LocalImageAgent MCP Server
`$ScriptDir = Split-Path -Parent `$MyInvocation.MyCommand.Path
`$PythonExe = Join-Path `$ScriptDir ".venv\Scripts\python.exe"
`$MainPy    = Join-Path `$ScriptDir "src\main.py"
& `$PythonExe `$MainPy
"@

[System.IO.File]::WriteAllText($LauncherFile, $launcherContent, [System.Text.UTF8Encoding]::new($false))
Write-OK "run_server.ps1 created"

# ---------------------------------------------------------------------------
# 7. Print MCP client config example
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "  MCP Client Configuration Example" -ForegroundColor White
Write-Host "------------------------------------------------------------" -ForegroundColor DarkGray

$escapedPython = $PythonExe -replace '\\', '\\'
$escapedMain   = (Join-Path $SrcDir "main.py") -replace '\\', '\\'

$mcpConfig = @"
{
  "mcpServers": {
    "local-image-agent": {
      "command": "$escapedPython",
      "args": ["$escapedMain"],
      "disabled": false,
      "autoApprove": []
    }
  }
}
"@

Write-Host $mcpConfig -ForegroundColor Gray
Write-Host "------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Add the above to your MCP client config (e.g. Claude Desktop, Kiro mcp.json)." -ForegroundColor White
Write-Host ""

# ---------------------------------------------------------------------------
# 8. Start the server
# ---------------------------------------------------------------------------
Write-Step "Starting LocalImageAgent MCP server..."
Write-Host "    Press Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

& $PythonExe (Join-Path $SrcDir "main.py")
