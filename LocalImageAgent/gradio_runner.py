"""
Wrapper: runs gradio_app.py, captures output, saves public URL,
and pushes it to git so it's remotely accessible.
"""
import subprocess, sys, os, threading
from pathlib import Path

BASE   = Path(__file__).parent
PYTHON = BASE / ".venv" / "Scripts" / "python.exe"
APP    = BASE / "gradio_app.py"
LOGF   = BASE / "gradio_all.log"
URLF   = BASE / "gradio_url.txt"

env = os.environ.copy()
env["GRADIO_TEMP_DIR"] = str(BASE / "gradio_outputs")
env["USERPROFILE"]     = str(BASE)
env["HOME"]            = str(BASE)

proc = subprocess.Popen(
    [str(PYTHON), "-u", str(APP)],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True, bufsize=1,
    cwd=str(BASE),
    env=env,
    creationflags=subprocess.CREATE_NO_WINDOW,
)

url_found = False

def _git_push_url(url: str):
    """Write URL to file and push to git."""
    try:
        import subprocess as sp
        URLF.write_text(url)
        # Run git from the actual repo root (BASE itself is the repo)
        sp.run(["git", "add", "gradio_url.txt"], cwd=str(BASE), capture_output=True)
        sp.run(["git", "commit", "-m", "chore: update gradio public URL"], cwd=str(BASE), capture_output=True)
        sp.run(["git", "push"], cwd=str(BASE), capture_output=True)
    except Exception:
        pass

def reader(stream, log):
    global url_found
    for line in stream:
        log.write(line)
        log.flush()
        if not url_found and "gradio.live" in line:
            for word in line.split():
                if word.startswith("https://") and "gradio.live" in word:
                    url_found = True
                    _git_push_url(word.strip())
                    break

with open(LOGF, "w", encoding="utf-8") as log:
    t1 = threading.Thread(target=reader, args=(proc.stdout, log), daemon=True)
    t2 = threading.Thread(target=reader, args=(proc.stderr, log), daemon=True)
    t1.start(); t2.start()
    proc.wait()
    t1.join(timeout=5); t2.join(timeout=5)
