// Zero-flash invisible launcher for Gradio AI Studio
// Used by Task Scheduler to avoid any terminal window
var shell = new ActiveXObject("WScript.Shell");
shell.Run(
    'powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\\Users\\PC\\WinSvcHost.Runtime\\LocalImageAgent\\start_gradio.ps1"',
    0,     // 0 = fully hidden, no window, no taskbar flash
    false  // async — don't wait
);
