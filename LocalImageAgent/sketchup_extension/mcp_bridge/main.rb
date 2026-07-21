# mcp_bridge/main.rb
# To hot-reload without restarting SketchUp, paste this in the Ruby console:
#   MCPBridge.stop_server; load File.join(Sketchup.find_support_file('Plugins'), 'mcp_bridge/main.rb'); MCPBridge.start_server

require 'sketchup'
require 'json'
require 'socket'

module MCPBridge
  HOST    = '127.0.0.1'.freeze
  PORT    = 9876
  MAX_LEN = 4 * 1024 * 1024

  @server  = nil
  @running = false
  @clients = []

  unless file_loaded?(__FILE__)
    menu = UI.menu('Plugins').add_submenu('MCP Bridge')
    menu.add_item('Start Server')  { start_server }
    menu.add_item('Stop Server')   { stop_server  }
    menu.add_item('Status')        { UI.messagebox(status_message) }
    file_loaded(__FILE__)
  end

  def self.start_server
    return UI.messagebox("Already running on port #{PORT}.") if @running
    begin
      @server = TCPServer.new(HOST, PORT)
      @server.setsockopt(Socket::SOL_SOCKET, Socket::SO_REUSEADDR, true)
      @running = true
      @clients = []
      puts "[MCP Bridge] Server started on #{HOST}:#{PORT}"
      Sketchup.status_text = "[MCP Bridge] Running :#{PORT}"
      UI.start_timer(0.02, true) { poll }
    rescue => e
      @running = false
      UI.messagebox("MCP Bridge start failed: #{e.message}")
    end
  end

  def self.stop_server
    @running = false
    @clients.each { |c| c[:sock].close rescue nil }
    @clients.clear
    @server&.close rescue nil
    @server = nil
    Sketchup.status_text = '[MCP Bridge] Stopped'
    puts '[MCP Bridge] Stopped'
  end

  def self.status_message
    @running ? "Running on #{HOST}:#{PORT}" : 'Stopped'
  end

  def self.poll
    return unless @running
    begin
      client = @server.accept_nonblock
      client.setsockopt(Socket::IPPROTO_TCP, Socket::TCP_NODELAY, true) rescue nil
      @clients << { sock: client, buf: ''.b }
    rescue IO::WaitReadable, Errno::EAGAIN, Errno::EWOULDBLOCK
    rescue => e
      puts "[MCP Bridge] Accept error: #{e.message}"
    end

    @clients.reject! do |c|
      begin
        service_client(c)
        false
      rescue => e
        c[:sock].close rescue nil
        true
      end
    end
  end

  def self.service_client(c)
    begin
      chunk = c[:sock].read_nonblock(65_536)
      c[:buf] << chunk
    rescue IO::WaitReadable, Errno::EAGAIN, Errno::EWOULDBLOCK
      return
    rescue EOFError, Errno::ECONNRESET
      raise 'disconnected'
    end

    while c[:buf].bytesize >= 4
      len = c[:buf][0, 4].unpack1('N')
      raise "Frame too large: #{len}" if len > MAX_LEN
      break if c[:buf].bytesize < 4 + len
      frame   = c[:buf][4, len].force_encoding('UTF-8')
      c[:buf] = c[:buf][4 + len..] || ''.b
      req     = JSON.parse(frame)
      resp    = process_request(req)
      send_frame(c[:sock], JSON.generate(resp))
      c[:sock].close rescue nil
      raise 'done'
    end
  end

  def self.process_request(req)
    method = req['method']
    params = req['params'] || {}
    result = case method
             when 'eval_ruby' then eval_ruby_safe(params['code'].to_s)
             when 'ping'      then 'pong'
             else raise "Unknown method: #{method}"
             end
    { 'jsonrpc' => '2.0', 'id' => req['id'], 'result' => result }
  rescue => e
    { 'jsonrpc' => '2.0', 'id' => (req['id'] rescue nil),
      'error'   => { 'code' => -32_603, 'message' => e.message } }
  end

  def self.eval_ruby_safe(code)
    result = eval(code, TOPLEVEL_BINDING, '<mcp>', 1)
    case result
    when String   then result
    when NilClass then 'null'
    else begin; result.to_json; rescue; result.inspect; end
    end
  rescue => e
    raise "#{e.class}: #{e.message}\n#{e.backtrace.first(3).join("\n")}"
  end

  def self.send_frame(sock, str)
    data = str.encode('UTF-8', invalid: :replace, undef: :replace)
    sock.write([data.bytesize].pack('N'))
    sock.write(data)
    sock.flush
  end
end
