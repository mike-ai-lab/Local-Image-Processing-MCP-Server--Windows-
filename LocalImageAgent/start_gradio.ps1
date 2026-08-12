# Starts Gradio AI Studio only (MCP server + ngrok managed separately)
# Safe to run at any time — only touches port 7860

$Base   = "C:\Users\PC\WinSvcHost.Runtime\LocalImageAgent"
$Python = "$Base\.venv\Scripts\python.exe"

# Kill only existing Gradio instance
Get-WmiObject Win32_Process | Where-Object {
    $_.CommandLine -like "*gradio_app*"
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

Start-Sleep 2

# Start Gradio AI Studio
Start-Process $Python `
    -ArgumentList "-u `"$Base\gradio_runner.py`"" `
    -WindowStyle Hidden
