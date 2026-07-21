import sys
sys.path.insert(0, 'LocalImageAgent/src')

try:
    import pystray
    print("pystray ok:", pystray.__version__ if hasattr(pystray,'__version__') else "installed")
except Exception as e:
    print("pystray FAIL:", e)

try:
    from PIL import Image, ImageDraw
    print("PIL ok")
except Exception as e:
    print("PIL FAIL:", e)

try:
    import subprocess, threading, time, socket
    print("stdlib ok")
except Exception as e:
    print("stdlib FAIL:", e)

# Try importing the actual tray module
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("tray", "LocalImageAgent/tray.py")
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    print("tray.py imports ok")
except Exception as e:
    print("tray.py FAIL:", e)
    import traceback; traceback.print_exc()
