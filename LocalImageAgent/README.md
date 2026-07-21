# LocalImageAgent — Local Media & File MCP Server

A Windows MCP server that exposes image processing, video processing, file system, and vision analysis tools to any MCP-compatible AI client (ChatGPT, Claude, etc.) via a permanent HTTPS endpoint. Powered by ImageMagick, FFmpeg, and FastMCP.

---

## MCP Endpoint

```
https://pectin-parting-caution.ngrok-free.dev/mcp
```

This URL is permanent — add it once in your ChatGPT connector settings and never touch it again.

---

## Requirements

- Windows 10/11
- Python 3.13+
- [ImageMagick 7](https://imagemagick.org/script/download.php#windows) — installed and on PATH
- [FFmpeg](https://ffmpeg.org/download.html) — installed and on PATH
- ngrok account (free tier, already configured)

---

## First-time setup

```powershell
.\bootstrap.ps1
.\install_autostart.ps1
```

`bootstrap.ps1` creates the virtual environment, installs dependencies, detects ImageMagick, and generates `config.json`.
`install_autostart.ps1` registers the tray app to launch automatically at every Windows login.

---

## Starting the server

**Desktop shortcut (recommended)**
Double-click `Image MCP Server` on the Desktop.

**PowerShell**
```powershell
.\start.ps1
```

The tray icon in the system tray shows server status:
- Green = running and reachable
- Red = stopped

Right-click the tray icon to start, stop, or quit. The server auto-starts at login if `install_autostart.ps1` has been run.

---

## Connecting to ChatGPT Desktop

1. Settings → Apps & Connectors → Add Custom Plugin
2. MCP Server URL: `https://pectin-parting-caution.ngrok-free.dev/mcp`
3. Authentication: No Auth → confirm

Done once per ChatGPT account. Works from any device on that account.

---

## Tools

### Image processing

| Tool | Description |
|---|---|
| `compress_image` | Compress a single image, optionally to a max KB target using binary search |
| `compress_folder` | Compress all images in a folder |
| `resize_image` | Resize with fit / fill / exact modes |
| `batch_resize` | Resize all images in a folder |
| `convert_image` | Convert between JPG, PNG, WebP, AVIF, TIFF, BMP |
| `batch_convert` | Convert all images in a folder to a target format |
| `strip_metadata` | Remove EXIF and all metadata |
| `image_info` | Return format, dimensions, color space, DPI, file size, metadata |
| `create_thumbnail` | Generate a thumbnail preserving aspect ratio |

### Video processing

| Tool | Description |
|---|---|
| `video_info` | Return codec, resolution, fps, duration, bitrate, audio info |
| `video_pipeline` | Run multiple operations as a single transaction (trim + compress + strip + speed + social) |
| `compress_video` | Compress a video, optionally targeting a max file size in MB |
| `trim_video` | Cut a video to a time range (HH:MM:SS or seconds) |
| `strip_video_metadata` | Remove all metadata from a video |
| `adjust_video` | Change speed, add frame interpolation for smoothness, apply sharpening |
| `optimize_for_social` | Re-encode for Instagram, TikTok, YouTube, Twitter, Facebook, or LinkedIn |
| `batch_optimize_social` | Optimise all videos in a folder for a platform |

### File system

| Tool | Description |
|---|---|
| `read_file` | Read any text file, optionally a line range |
| `write_file` | Create or overwrite a file |
| `edit_file` | Find and replace inside a file (literal or regex) |
| `list_directory` | List files and folders, optionally recursive |
| `find_files` | Find files by name — fast, skips system folders, supports wildcards |
| `search_files` | Search text content across files with timeout and file count limits |
| `delete_path` | Delete a file or folder (requires confirm: true) |
| `create_directory` | Create a folder and any missing parents |
| `move_path` | Move or rename a file or folder |

### Vision analysis

| Tool | Description |
|---|---|
| `read_image_for_vision` | Read one image as a base64 JPEG thumbnail for ChatGPT vision analysis |
| `read_folder_for_vision` | Read a batch of images for vision analysis — sorted, capped, never overloads device |

`read_folder_for_vision` supports:
- `sort_by`: newest (default) / oldest / name
- `modified_within_hours`: only images from the last N hours
- `max_images`: hard cap before encoding (default 30, max 100)

Use for: renaming images by content, finding images by scene or object, comparing shots, selecting the best angle.

---

## Supported formats

| | Formats |
|---|---|
| Image input | JPG, JPEG, PNG, TIFF, BMP, GIF, WebP, AVIF |
| Image output | JPG, PNG, TIFF, BMP, WebP, AVIF |
| Video input | MP4, MOV, AVI, MKV, WMV, WebM, FLV, M4V, TS, MTS |
| Video output | MP4, MOV, AVI, MKV, WebM |

---

## Project structure

```
LocalImageAgent/
├── tray.py                    # System tray controller (green/red icon)
├── start.ps1                  # PowerShell launcher
├── bootstrap.ps1              # First-time setup
├── install_autostart.ps1      # Register auto-start at login
├── remove_autostart.ps1       # Remove auto-start
├── create_shortcut.ps1        # Create desktop shortcut
├── requirements.txt
├── config.json
├── agent.log                  # Tool-level log with timing (rotating, 5MB x3)
├── server.log                 # HTTP access log
├── ngrok/
│   └── ngrok.exe
└── src/
    ├── main_http.py           # Server entry point — Streamable HTTP (ChatGPT)
    ├── main.py                # Server entry point — stdio (Claude Desktop)
    ├── config.py              # Configuration loader
    ├── log_setup.py           # Rich console + rotating file logging
    ├── imagemagick.py         # ImageMagick subprocess wrapper
    ├── process.py             # Image processing core
    ├── tools.py               # Image MCP tool definitions
    ├── ffmpeg.py              # FFmpeg subprocess wrapper
    ├── video_process.py       # Video processing core
    ├── video_tools.py         # Video MCP tool definitions
    ├── file_process.py        # File system operations
    ├── file_tools.py          # File MCP tool definitions
    ├── image_vision.py        # Base64 vision thumbnail generator
    ├── vision_tools.py        # Vision MCP tool definitions
    └── validation.py          # Input validation helpers
```

---

## Logs

`agent.log` — persistent rotating log of every tool call with timing and errors. Check this for debugging.
`server.log` — HTTP access log (uvicorn requests).

---

## Configuration

`config.json` is auto-generated by `bootstrap.ps1`. Only edit if ImageMagick is in a non-standard location.

```json
{
  "magick_exe": "C:\\Program Files\\ImageMagick-7.1.1-Q16-HDRI\\magick.exe",
  "log_level": "INFO"
}
```

---

## Removing auto-start

```powershell
.\remove_autostart.ps1
```
