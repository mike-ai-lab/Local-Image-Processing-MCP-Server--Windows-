#Requires -Version 5.1
# Removes the auto-start registration added by install_autostart.ps1

$RegKey  = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$AppName = "LocalImageAgent"

Remove-ItemProperty -Path $RegKey -Name $AppName -ErrorAction SilentlyContinue
Write-Host ""
Write-Host "  [OK] Auto-start removed. The tray icon will no longer launch at login." -ForegroundColor Yellow
Write-Host ""
