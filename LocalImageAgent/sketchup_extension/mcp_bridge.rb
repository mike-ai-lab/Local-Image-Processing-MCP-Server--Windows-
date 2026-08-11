# mcp_bridge.rb — MCP Bridge loader
#
# Load this file directly from the Ruby console (no installation needed):
#   load 'C:/path/to/LocalImageAgent/sketchup_extension/mcp_bridge.rb'
#
# After loading, the server starts automatically.
#
# -----------------------------------------------------------------------
# Console commands:
#   MCPBridge.start_server   — start the TCP server
#   MCPBridge.stop_server    — stop the TCP server
#   MCPBridge.reload         — reload main.rb from disk and restart
#   MCPBridge.status_message — show current status
# -----------------------------------------------------------------------

require 'sketchup'
require 'json'
require 'socket'

# Resolve main.rb relative to this loader file — works from any location
MPCBRIDGE_MAIN = File.join(File.dirname(File.expand_path(__FILE__)), 'mcp_bridge', 'main.rb')

# Load main.rb which defines all MCPBridge methods
load MPCBRIDGE_MAIN

module MCPBridge
  # Reload main.rb from disk and restart the server cleanly.
  # Use this after editing main.rb — no SketchUp restart needed.
  def self.reload
    was_running = (@running rescue false)
    stop_server if was_running

    # Clear from Ruby's require cache so load re-reads from disk
    $LOADED_FEATURES.delete_if { |f| f.include?('mcp_bridge/main') }

    load MPCBRIDGE_MAIN
    puts "[MCP Bridge] Reloaded: #{MPCBRIDGE_MAIN}"

    start_server if was_running
    true
  end
end

# Auto-start on load
MCPBridge.start_server
