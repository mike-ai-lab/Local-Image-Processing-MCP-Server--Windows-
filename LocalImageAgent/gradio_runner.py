"""
Runs gradio_app.py + dedicated ngrok2 tunnel.
URL is always: https://maternal-wolf-trophy.ngrok-free.dev
Pushes URL to git on start.
Auto-restarts gradio if it crashes.
"""
import subprocess, sys, os, threading, time
from pathlib import Path

BASE    = Path(__file__).parent
PYTHON  = BASE / ".venv" / "Scripts" / "python.exe"
APP     = BASE / "gradio_app.py"
NGROK2  = BASE / "ngrok" / "ngrok2.exe"
NGROK2_CFG = BASE / "ngrok" / "ngrok2.yml"
LOGF    = BASE / "gradio_all.log"
URLF    = BASE / "gradio_url.txt"
DOMAIN  = "maternal-wolf-trophy.ngrok-free.dev"
PORT    = 7861

env = os.environ.copy()
env["GRADIO_TEMP_DIR"] = str(BASE / "gradio_outputs")
env["USERPROFILE"]     = str(BASE)
env["HOME"]            = str(BASE)


def _git_push_url(url: str):
    try:
        URLF.write_text(url)
        subprocess.run(["git", "add", "-f", "gradio_url.txt"], cwd=str(BASE), capture_output=True)
        subprocess.run(["git", "commit", "-m", "chore: update gradio URL"], cwd=str(BASE), capture_output=True)
        subprocess.run(["git", "push"], cwd=str(BASE), capture_output=True)
    except Exception:
        pass


def _stream(stream, log):
    for line in stream:
        try:
            log.write(line)
            log.flush()
        except Exception:
            pass


# Write and push the fixed URL immediately
_url = f"https://{DOMAIN}"
threading.Thread(target=_git_push_url, args=(_url,), daemon=True).start()

# Kill any existing ngrok2 / gradio on our port
subprocess.run(f"taskkill /F /IM ngrok2.exe", shell=True, capture_output=True)
for proc in subprocess.run("netstat -ano", shell=True, capture_output=True, text=True).stdout.splitlines():
    if f":{PORT} " in proc and "LISTENING" in proc:
        pid = proc.strip().split()[-1]
        subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
time.sleep(2)

# Start ngrok2 tunnel (dedicated account, stable domain)
ngrok_proc = subprocess.Popen(
    [str(NGROK2), "http", str(PORT), f"--domain={DOMAIN}",
     f"--config={NGROK2_CFG}"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    creationflags=subprocess.CREATE_NO_WINDOW,
)
time.sleep(3)

# Gradio auto-restart loop
while True:
    proc = subprocess.Popen(
        [str(PYTHON), "-u", str(APP)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True, bufsize=1,
        cwd=str(BASE),
        env=env,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    with open(LOGF, "a", encoding="utf-8") as log:
        t1 = threading.Thread(target=_stream, args=(proc.stdout, log), daemon=True)
        t2 = threading.Thread(target=_stream, args=(proc.stderr, log), daemon=True)
        t1.start(); t2.start()
        proc.wait()
        t1.join(timeout=3); t2.join(timeout=3)

    time.sleep(10)  # wait before restart
