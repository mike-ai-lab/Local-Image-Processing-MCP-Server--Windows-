# mcp_bridge/main.rb
# Hot-reload: paste in Ruby console to reload without restarting SketchUp:
#   MCPBridge.stop_server; load File.join(Sketchup.find_support_file('Plugins'), 'mcp_bridge/main.rb'); MCPBridge.start_server

require 'sketchup'
require 'json'
require 'socket'

module MCPBridge
  HOST    = '127.0.0.1'.freeze
  PORT    = 9876
  VERSION = '2.0.0'.freeze

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

  # ---------------------------------------------------------------------------
  # Server lifecycle
  # ---------------------------------------------------------------------------

  def self.start_server
    return UI.messagebox("MCP Bridge is already running on port #{PORT}.") if @running
    begin
      @server = TCPServer.new(HOST, PORT)
      @server.setsockopt(Socket::SOL_SOCKET, Socket::SO_REUSEADDR, true)
      @running = true
      @clients = []
      puts "[MCP Bridge] Server started on #{HOST}:#{PORT} (v#{VERSION})"
      Sketchup.status_text = "[MCP Bridge] Running :#{PORT}"
      UI.start_timer(0.02, true) { poll }
    rescue => e
      @running = false
      UI.messagebox("MCP Bridge failed to start: #{e.message}")
    end
  end

  def self.stop_server
    @running = false
    @clients.each { |c| c[:sock].close rescue nil }
    @clients.clear
    @server&.close rescue nil
    @server = nil
    Sketchup.status_text = '[MCP Bridge] Stopped'
    puts '[MCP Bridge] Server stopped'
  end

  def self.status_message
    @running ? "Running on #{HOST}:#{PORT} (v#{VERSION})" : 'Stopped'
  end

  # ---------------------------------------------------------------------------
  # Poll loop — called every 20ms by UI.start_timer
  # ---------------------------------------------------------------------------

  def self.poll
    return unless @running

    # Accept new connections (non-blocking)
    begin
      client = @server.accept_nonblock
      client.setsockopt(Socket::IPPROTO_TCP, Socket::TCP_NODELAY, true) rescue nil
      @clients << { sock: client, buf: '' }
      puts "[MCP Bridge] Client connected"
    rescue IO::WaitReadable, Errno::EAGAIN, Errno::EWOULDBLOCK
    rescue => e
      puts "[MCP Bridge] Accept error: #{e.message}"
    end

    # Service existing clients
    @clients.reject! do |c|
      begin
        service_client(c)
        false
      rescue => e
        msg = e.message
        puts "[MCP Bridge] Client disconnected: #{msg}" unless msg == 'done'
        c[:sock].close rescue nil
        true
      end
    end
  end

  # ---------------------------------------------------------------------------
  # Per-client service — reads newline-delimited JSON
  # ---------------------------------------------------------------------------

  def self.service_client(c)
    # Non-blocking read — accumulate into buffer
    begin
      chunk = c[:sock].read_nonblock(65_536)
      c[:buf] << chunk
    rescue IO::WaitReadable, Errno::EAGAIN, Errno::EWOULDBLOCK
      return  # nothing to read yet
    rescue EOFError, Errno::ECONNRESET, Errno::EPIPE
      raise 'disconnected'
    end

    # Process all complete newline-delimited messages in buffer
    while (nl = c[:buf].index("\n"))
      line      = c[:buf][0, nl].strip
      c[:buf]   = c[:buf][nl + 1..] || ''
      next if line.empty?

      begin
        req  = JSON.parse(line)
        resp = process_request(req)
        begin
          json = JSON.generate(resp) + "\n"
        rescue => je
          json = JSON.generate({
            'jsonrpc' => '2.0', 'id' => (req['id'] rescue nil),
            'error' => { 'code' => -32603, 'message' => "Serialization error: #{je.message}" }
          }) + "\n"
        end
        c[:sock].write(json)
        c[:sock].flush
      rescue JSON::ParserError => e
        err = JSON.generate({
          'jsonrpc' => '2.0', 'id' => nil,
          'error'   => { 'code' => -32700, 'message' => "Parse error: #{e.message}" }
        }) + "\n"
        c[:sock].write(err)
        c[:sock].flush
      end

      # One request per connection (matches Python bridge expectations)
      c[:sock].close rescue nil
      raise 'done'
    end
  end

  # ---------------------------------------------------------------------------
  # Request dispatcher
  # ---------------------------------------------------------------------------

  def self.process_request(req)
    id     = req['id']
    method = req['method'].to_s
    params = req['params'] || {}

    # Support both direct method calls and tools/call envelope
    if method == 'tools/call'
      method = params['name'].to_s
      params = params['arguments'] || {}
    end

    result = dispatch(method, params)
    { 'jsonrpc' => '2.0', 'id' => id, 'result' => result }
  rescue => e
    { 'jsonrpc' => '2.0', 'id' => (req['id'] rescue nil),
      'error'   => { 'code' => -32_603, 'message' => "#{e.class}: #{e.message}" } }
  end

  def self.dispatch(method, params)
    case method
    when 'ping'              then 'pong'
    when 'eval_ruby'         then eval_ruby_safe(params['code'].to_s)
    when 'get_scene_info'    then get_scene_info
    when 'get_selection'     then get_selection
    when 'create_component'  then create_component(params)
    when 'delete_component'  then delete_component(params)
    when 'transform_component' then transform_component(params)
    when 'set_material'      then set_material(params)
    when 'export_scene'      then export_scene(params)
    else
      raise "Unknown method: #{method}"
    end
  end

  # ---------------------------------------------------------------------------
  # eval_ruby — arbitrary Ruby execution
  # ---------------------------------------------------------------------------

  def self.eval_ruby_safe(code)
    result = eval(code, TOPLEVEL_BINDING, '<mcp>', 1)
    # Ensure result is JSON-serialisable
    case result
    when String, NilClass, TrueClass, FalseClass, Integer, Float
      result
    when Hash, Array
      # Re-encode through JSON to catch any non-serialisable values
      begin
        JSON.parse(JSON.generate(result))
      rescue
        result.inspect
      end
    else
      begin
        JSON.parse(result.to_json)
      rescue
        result.inspect
      end
    end
  rescue SyntaxError => e
    { 'ruby_error' => true, 'error_class' => 'SyntaxError',
      'message' => e.message.lines.first(3).join(' ').strip }
  rescue => e
    { 'ruby_error' => true, 'error_class' => e.class.to_s,
      'message' => e.message,
      'backtrace' => e.backtrace.first(3) }
  end

  # ---------------------------------------------------------------------------
  # Named command handlers
  # ---------------------------------------------------------------------------

  def self.get_scene_info
    m    = Sketchup.active_model
    view = m.active_view
    cam  = view.camera

    components = m.entities.grep(Sketchup::ComponentInstance).map do |e|
      t = e.transformation
      {
        'id'         => e.entityID.to_s,
        'name'       => e.definition.name,
        'position'   => [t.origin.x.to_f, t.origin.y.to_f, t.origin.z.to_f],
        'visible'    => e.visible?,
        'layer'      => e.layer.name,
      }
    end

    groups = m.entities.grep(Sketchup::Group).map do |g|
      t = g.transformation
      {
        'id'       => g.entityID.to_s,
        'name'     => g.name,
        'position' => [t.origin.x.to_f, t.origin.y.to_f, t.origin.z.to_f],
        'visible'  => g.visible?,
        'layer'    => g.layer.name,
      }
    end

    materials = m.materials.map do |mat|
      c = mat.color
      {
        'name'  => mat.name,
        'color' => [c.red, c.green, c.blue, c.alpha],
      }
    end

    layers = m.layers.map { |l| { 'name' => l.name, 'visible' => l.visible? } }

    {
      'model_name'  => m.name,
      'model_path'  => m.path,
      'face_count'  => m.entities.grep(Sketchup::Face).count,
      'edge_count'  => m.entities.grep(Sketchup::Edge).count,
      'components'  => components,
      'groups'      => groups,
      'materials'   => materials,
      'layers'      => layers,
      'camera'      => {
        'eye'       => cam.eye.to_a.map(&:to_f),
        'target'    => cam.target.to_a.map(&:to_f),
        'up'        => cam.up.to_a.map(&:to_f),
        'fov'       => cam.fov.to_f,
        'perspective' => cam.perspective?,
      }
    }
  end

  def self.get_selection
    m = Sketchup.active_model
    m.selection.map do |e|
      info = { 'id' => e.entityID.to_s, 'type' => e.class.name }
      if e.respond_to?(:definition)
        info['name'] = e.definition.name
        t = e.transformation
        info['position'] = [t.origin.x.to_f, t.origin.y.to_f, t.origin.z.to_f]
      elsif e.is_a?(Sketchup::Group)
        info['name'] = e.name
        t = e.transformation
        info['position'] = [t.origin.x.to_f, t.origin.y.to_f, t.origin.z.to_f]
      end
      info
    end
  end

  def self.create_component(params)
    m    = Sketchup.active_model
    type = (params['type'] || 'cube').downcase
    pos  = params['position']  || [0, 0, 0]
    dims = params['dimensions'] || [1, 1, 1]

    # Convert meters to inches (SketchUp internal unit)
    to_in = 39.3701
    x, y, z = pos[0].to_f * to_in, pos[1].to_f * to_in, pos[2].to_f * to_in
    w, d, h = dims[0].to_f * to_in, dims[1].to_f * to_in, dims[2].to_f * to_in

    m.start_operation("MCP Create #{type}", true)
    grp = m.entities.add_group

    case type
    when 'cube', 'box'
      pts  = [
        Geom::Point3d.new(x,   y,   z),
        Geom::Point3d.new(x+w, y,   z),
        Geom::Point3d.new(x+w, y+d, z),
        Geom::Point3d.new(x,   y+d, z)
      ]
      face = grp.entities.add_face(pts)
      face.pushpull(h)
    when 'cylinder'
      center = Geom::Point3d.new(x + w/2, y + d/2, z)
      radius = [w, d].min / 2
      circle = grp.entities.add_circle(center, Z_AXIS, radius, 24)
      face   = grp.entities.add_face(circle)
      face.pushpull(h)
    when 'sphere'
      # Approximated as a 24-segment sphere via follow_me
      center = Geom::Point3d.new(x, y, z)
      radius = [w, d, h].min / 2
      circle_path = grp.entities.add_circle(center, Z_AXIS, radius, 24)
      semi = grp.entities.add_arc(center, X_AXIS, Z_AXIS, radius, 0, Math::PI, 24)
      semi_face = grp.entities.add_face(semi + [Geom::Point3d.new(center.x, center.y, center.z + radius), Geom::Point3d.new(center.x, center.y, center.z - radius)])
      semi_face.followme(circle_path) rescue nil
    end

    m.commit_operation

    t = grp.transformation
    {
      'id'         => grp.entityID.to_s,
      'type'       => type,
      'position'   => [t.origin.x.to_f, t.origin.y.to_f, t.origin.z.to_f],
      'dimensions' => dims,
    }
  end

  def self.delete_component(params)
    m   = Sketchup.active_model
    id  = params['id'].to_s
    ent = m.find_entity_by_id(id.to_i)
    raise "Entity #{id} not found" unless ent
    m.start_operation('MCP Delete', true)
    m.entities.erase_entities(ent)
    m.commit_operation
    { 'deleted' => id }
  end

  def self.transform_component(params)
    m   = Sketchup.active_model
    id  = params['id'].to_s
    ent = m.find_entity_by_id(id.to_i)
    raise "Entity #{id} not found" unless ent

    to_in = 39.3701
    m.start_operation('MCP Transform', true)

    if (pos = params['position'])
      origin = Geom::Point3d.new(pos[0].to_f * to_in, pos[1].to_f * to_in, pos[2].to_f * to_in)
      ent.move!(Geom::Transformation.new(origin))
    end

    if (rot = params['rotation'])
      rx = Geom::Transformation.rotation(ORIGIN, X_AXIS, rot[0].to_f.degrees)
      ry = Geom::Transformation.rotation(ORIGIN, Y_AXIS, rot[1].to_f.degrees)
      rz = Geom::Transformation.rotation(ORIGIN, Z_AXIS, rot[2].to_f.degrees)
      ent.transform!(rx * ry * rz)
    end

    if (sc = params['scale'])
      ent.transform!(Geom::Transformation.scaling(sc[0].to_f, sc[1].to_f, sc[2].to_f))
    end

    m.commit_operation
    t = ent.transformation
    { 'id' => id, 'position' => [t.origin.x.to_f, t.origin.y.to_f, t.origin.z.to_f] }
  end

  def self.set_material(params)
    m      = Sketchup.active_model
    id     = params['id'].to_s
    mat_in = params['material'].to_s

    ent = m.find_entity_by_id(id.to_i)
    raise "Entity #{id} not found" unless ent

    m.start_operation('MCP Set Material', true)

    # Parse color — support hex (#rrggbb), rgb(r,g,b), or named material
    mat = if mat_in.start_with?('#')
      hex = mat_in.sub('#', '')
      r, g, b = hex[0,2].to_i(16), hex[2,2].to_i(16), hex[4,2].to_i(16)
      new_mat = m.materials.add("MCP_#{hex}")
      new_mat.color = Sketchup::Color.new(r, g, b)
      new_mat
    elsif mat_in.start_with?('rgb')
      nums = mat_in.scan(/\d+/).map(&:to_i)
      new_mat = m.materials.add("MCP_#{nums.join('_')}")
      new_mat.color = Sketchup::Color.new(*nums)
      new_mat
    else
      m.materials[mat_in] || begin
        new_mat = m.materials.add(mat_in)
        new_mat.color = Sketchup::Color.new(mat_in) rescue Sketchup::Color.new(200, 200, 200)
        new_mat
      end
    end

    # Apply to entity and all its faces
    ent.material = mat
    faces = if ent.respond_to?(:definition)
      ent.definition.entities.grep(Sketchup::Face)
    elsif ent.is_a?(Sketchup::Group)
      ent.entities.grep(Sketchup::Face)
    else
      []
    end
    faces.each { |f| f.material = mat }

    m.commit_operation
    { 'id' => id, 'material' => mat.name, 'color' => mat.color.to_a }
  end

  def self.export_scene(params)
    m      = Sketchup.active_model
    fmt    = (params['format'] || 'skp').downcase
    path   = m.path
    raise "Model has not been saved — save it first" if path.nil? || path.empty?

    dir    = File.dirname(path)
    base   = File.basename(path, '.*')
    output = File.join(dir, "#{base}_export.#{fmt}")

    case fmt
    when 'skp'
      m.save(output)
    when 'stl'
      m.export(output) rescue raise("STL export requires the SketchUp STL extension")
    when 'obj'
      m.export(output) rescue raise("OBJ export failed")
    when 'dae', 'collada'
      m.export(output)
    else
      raise "Unsupported export format: #{fmt}. Supported: skp, stl, obj, dae"
    end

    { 'path' => output, 'format' => fmt }
  end
end
