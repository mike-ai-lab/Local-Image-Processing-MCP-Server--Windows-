---
inclusion: always
---

# User Environment Defaults

## Output File Location
When the user does not specify an output path, always default to:
- **Desktop**: `C:\Users\Administrator\Desktop\`
- Never use `C:\Users\Public`, temp folders, or working directory

## User Paths
- Desktop: `C:\Users\Administrator\Desktop`
- Downloads: `C:\Users\Administrator\Downloads`
- Current user home: `C:\Users\Administrator`

## MCP Server
- The local-image-agent MCP server is always running at `http://127.0.0.1:8765/mcp`
- SketchUp MCP Bridge runs on `127.0.0.1:9876` when SketchUp is open
- Always use MCP tools for file operations, image processing, and SketchUp tasks — never suggest the user run commands manually
