# LocalImageAgent MCP Server — Quick Start Guide

## What is this?

A locally-hosted MCP server that lets ChatGPT (and other AI clients) control:
- Image processing via ImageMagick (compress, resize, convert, enhance, denoise, etc.)
- Video processing via FFmpeg (compress, trim, speed, social media optimize)
- File system operations (read, write, edit, search, find files)
- Vision analysis (read local images for ChatGPT to analyze and generate variations)
- SketchUp + V-Ray workflows (scene analysis, materials, geometry, environment, camera)

The server runs on your Windows machine. ChatGPT connects to it through a permanent ngrok HTTPS tunnel.

---

## Fresh Setup (new machine)

### 1. Prerequisites
- Windows 10/11
- Python 3.10+ — https://www.python.org/downloads/ (check "Add to PATH")
- Git — https://git-scm.com

### 2. Clone and run setup

```powershell
git clone https://github.com/mike-ai-lab/Local-Image-Processing-MCP-Server--Windows-.git
cd "Local-Image-Processing-MCP-Server--Windows-"
.\LocalImageAgent\setup.ps1
```

`setup.ps1` handles everything automatically:
- Creates Python virtual environment
- Installs all dependencies
- Downloads ImageMagick if not found
- Downloads FFmpeg if not found
- Downloads and configures ngrok
- Writes `config.json`
- Creates desktop shortcut
- Registers tray app as Windows startup item

---

## Daily Use

**Double-click "Image MCP Server" on your desktop** — tray icon appears and turns green.

That's it. ChatGPT is now connected and can use all tools.

---

## ChatGPT Connector Setup (one time per account)

In ChatGPT Desktop → Settings → Apps & Connectors → Add Custom Plugin:

| Field | Value |
|---|---|
| MCP Server URL | `https://pectin-parting-caution.ngrok-free.dev/mcp` |
| Authentication | No Auth |

Check the disclaimer → confirm. The connector saves to your ChatGPT account and works from any device as long as this machine is running the tray app.

---

## SketchUp Integration

The server can control a live SketchUp instance. To activate:

1. Open SketchUp with your model
2. Open the Ruby console (Window → Ruby Console)
3. Paste and run:

```ruby
load 'C:/path/to/LocalImageAgent/sketchup_extension/mcp_bridge/main.rb'; MCPBridge.start_server
```

Replace the path with your actual clone location. You'll see:
```
[MCP Bridge] Server started on 127.0.0.1:9876 (v2.0.0)
```

To reload after updates (no SketchUp restart needed):
```ruby
MCPBridge.stop_server; load 'C:/path/to/LocalImageAgent/sketchup_extension/mcp_bridge/main.rb'; MCPBridge.start_server
```

---

## Manual Server Start (alternative to tray)

```powershell
.\LocalImageAgent\start.ps1
```

Keep the window open. Press Ctrl+C to stop.

---

## What ChatGPT can do — example prompts

**Images**
- "Compress `C:\Photos\photo.jpg` to under 300KB and save as `photo_small.jpg`"
- "Denoise and sharpen `C:\Renders\render.png` and save in place"
- "Convert all PNGs in `C:\Photos` to WebP"

**Video**
- "Compress `C:\Videos\clip.mp4` to under 50MB"
- "Trim `video.mp4` from 0:30 to 1:45 and speed it up 2x"
- "Optimize `C:\Videos\` folder for Instagram"

**Files**
- "Find all `.skb` files on my machine with the name STC-CRYSTAL"
- "Read `C:\Projects\app.js` and refactor the login function"
- "Search all `.py` files in `C:\Projects` for TODO comments"

**SketchUp** (requires MCP Bridge running in SketchUp)
- "Analyze my current SketchUp scene and report what needs fixing"
- "Create a polished marble material in SketchUp"
- "Explode the Wall_Display_Unit component and apply purple to the panels"
- "Capture a screenshot of my SketchUp viewport"
- "Diagnose why my render looks overexposed and fix the sun settings"
- "Get the V-Ray light count in my scene"

---

## Troubleshooting

**Tray icon stays red / server won't start**
- Check `LocalImageAgent\server_err.log` for the error
- Make sure port 8765 is free: `netstat -ano | findstr :8765`
- Kill stale processes: `taskkill /F /IM python.exe`

**ChatGPT says "connector unavailable"**
- Tray icon must be green before using tools
- ngrok URL is permanent — no need to re-add the connector

**SketchUp bridge hanging / no response**
- Reload the bridge in the Ruby console (see command above)
- One model at a time — close and reopen SketchUp if the bridge stops responding

**ImageMagick / FFmpeg not found**
- Re-run `setup.ps1` — it will detect and download what's missing
- Or install manually and update `config.json` with the correct paths

---

## File Structure

```
LocalImageAgent/
├── setup.ps1              ← run once on a new machine
├── start.ps1              ← manual server + ngrok launcher
├── tray.py                ← system tray app (double-click shortcut)
├── config.json            ← paths to ImageMagick, FFmpeg, server settings
├── requirements.txt
├── src/
│   ├── main_http.py       ← FastMCP server + all tool registrations
│   ├── tools.py           ← image processing tools
│   ├── video_tools.py     ← video processing tools
│   ├── file_tools.py      ← file system tools
│   ├── vision_tools.py    ← vision / image-to-generation tools
│   ├── sketchup_tools.py  ← SketchUp workflow tools
│   ├── sketchup_process.py← SketchUp high-level operations
│   ├── sketchup_bridge.py ← TCP client for SketchUp Ruby extension
│   └── ...
└── sketchup_extension/
    └── mcp_bridge/
        └── main.rb        ← load this in SketchUp Ruby console
```
