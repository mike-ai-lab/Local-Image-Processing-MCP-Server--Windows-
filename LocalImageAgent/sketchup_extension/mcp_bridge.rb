# mcp_bridge.rb — SketchUp MCP Bridge Extension loader
# Install this as an .rbz in SketchUp via Window > Extension Manager

require 'sketchup'
require 'extensions'

module MCPBridge
  VERSION = '1.0.0'.freeze
  EXTENSION = SketchupExtension.new('MCP Bridge', 'mcp_bridge/main')
  EXTENSION.description = 'TCP bridge allowing the LocalImageAgent MCP server to drive SketchUp.'
  EXTENSION.version     = VERSION
  EXTENSION.creator     = 'LocalImageAgent'
  Sketchup.register_extension(EXTENSION, true)
end
