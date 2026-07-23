"""High-level SketchUp + V-Ray workflow operations."""

from __future__ import annotations
import textwrap
from typing import Any
from sketchup_bridge import run_ruby_json

def _ruby(code: str) -> Any:
    return run_ruby_json(textwrap.dedent(code).strip())

def analyze_scene() -> dict[str, Any]:
    return _ruby("""
    m = Sketchup.active_model

    # Iterative traversal using a stack — no recursion, no stack overflow
    stack = [m.entities]
    faces = edges = instances = reversed = 0
    visited = {}

    until stack.empty?
      ents = stack.pop
      ents.each do |e|
        case e
        when Sketchup::Face
          faces += 1
          reversed += 1 if e.normal.z < 0
        when Sketchup::Edge
          edges += 1
        when Sketchup::Group
          instances += 1
          stack.push(e.entities)
        when Sketchup::ComponentInstance
          defn = e.definition
          unless visited[defn.object_id]
            visited[defn.object_id] = true
            stack.push(defn.entities)
          end
          instances += 1
        end
      end
    end

    mats = m.materials.map do |mat|
      tex = mat.texture
      { name: mat.name, color: mat.color.to_a,
        has_texture: !tex.nil?, texture_file: tex ? tex.filename : nil }
    end

    missing   = mats.select { |mm| mm[:has_texture] && mm[:texture_file] && !File.exist?(mm[:texture_file].to_s) }.map { |mm| mm[:texture_file] }
    mat_names = mats.map { |mm| mm[:name] }
    dupes     = mat_names.select { |n| mat_names.count(n) > 1 }.uniq

    # Top-level components only for the summary (avoid iterating everything again)
    defs = m.definitions.reject(&:image?).map do |d|
      { name: d.name, instances: d.instances.count,
        faces: d.entities.grep(Sketchup::Face).count }
    end

    {
      model_name:          m.name.empty? ? File.basename(m.path.to_s, ".skp") : m.name,
      model_path:          m.path,
      total_entities:      m.entities.count,
      total_faces:         faces,
      total_edges:         edges,
      total_instances:     instances,
      reversed_faces:      reversed,
      materials_count:     m.materials.count,
      missing_textures:    missing,
      duplicate_materials: dupes,
      tags_count:          m.layers.count,
      tags:                m.layers.map { |l| { name: l.name, visible: l.visible? } },
      components_count:    m.definitions.reject(&:image?).count,
      components:          defs,
      materials:           mats
    }
    """)

def prepare_scene_for_rendering(purge_unused=True, fix_reversed_faces=False, remove_hidden_geometry=False) -> dict[str, Any]:
    purge = "m.definitions.purge_unused; m.materials.purge_unused; m.layers.purge_unused; stats[:purged]=true" if purge_unused else ""
    fix   = "m.start_operation('Fix Reversed',true); reversed.each(&:reverse!); m.commit_operation; stats[:reversed_fixed]=reversed.count" if fix_reversed_faces else ""
    hidden= "hidden=m.entities.select(&:hidden?); m.start_operation('Remove Hidden',true); m.entities.erase_entities(hidden); m.commit_operation; stats[:hidden_removed]=hidden.count" if remove_hidden_geometry else ""
    return _ruby(f"""
    m=Sketchup.active_model; stats={{}}
    {purge}
    # Only check top-level faces to avoid flooding on complex models
    reversed=m.entities.grep(Sketchup::Face).select{{|f|f.normal.z<0}}
    stats[:reversed_faces_found]=reversed.count
    {fix}
    {hidden}
    stats[:status]="complete"; stats
    """)

def analyze_render_setup() -> dict[str, Any]:
    return _ruby("""
    m=Sketchup.active_model
    lights=m.entities.select{|e|e.is_a?(Sketchup::ComponentInstance)&&e.definition.name.to_s=~/vray|light|sun|sky|dome|ies/i}
           .map{|l|{name:l.definition.name,layer:l.layer.name,hidden:l.hidden?}}
    vray_mats=m.materials.select{|mat|mat.get_attribute("vray_props","reflection")!=nil}
              .map{|mat|{name:mat.name,reflection:mat.get_attribute("vray_props","reflection"),roughness:mat.get_attribute("vray_props","roughness")}}
    {model:m.name,vray_lights:lights,vray_materials:vray_mats,total_materials:m.materials.count,
     note:"Full V-Ray render settings require V-Ray SDK. Use V-Ray Asset Editor for deep inspection."}
    """)

def optimize_render_setup(goals: str = "") -> dict[str, Any]:
    return {
        "goals": goals,
        "recommendations": [
            "Set noise threshold to 0.005 for production quality",
            "Enable V-Ray denoiser (NVIDIA AI or V-Ray denoiser)",
            "Set GI to Brute Force + Light Cache for interiors",
            "Set GI to Brute Force + Brute Force for exteriors",
            "Use Light Cache subdivisions 1000+ for clean GI",
            "Clamp output to 6.0 to avoid fireflies",
            "Enable render elements: Diffuse, Reflection, GI, Denoiser",
        ],
        "note": "Automatic V-Ray setting changes require V-Ray SDK. Apply in V-Ray Asset Editor.",
        "status": "recommendations_generated"
    }

COLOR_MAP = {
    "purple":      (128,0,128),  "deep purple":(75,0,130),   "light purple":(180,120,200),
    "violet":      (138,43,226), "warm white": (255,245,230),"white":(255,255,255),
    "black":       (0,0,0),      "grey":       (128,128,128),"gray":(128,128,128),
    "red":         (220,50,50),  "blue":       (50,100,220), "green":(50,180,80),
    "gold":        (212,175,55), "brown":      (139,90,43),  "beige":(245,230,200),
    "orange":      (230,120,30), "yellow":     (240,220,50), "dark grey":(80,80,80),
    "cream":       (255,253,230),"navy":       (10,20,90),   "light grey":(200,200,200),
    "pink":        (255,105,180),"teal":       (0,128,128),  "cyan":(0,200,220),
    "dark blue":   (10,30,100),  "dark green":  (20,80,30),  "dark red":(120,10,10),
    "off white":   (245,243,238),"charcoal":   (50,50,55),   "bronze":(150,100,40),
    "silver":      (192,192,192),"copper":     (184,115,51), "rose":(220,130,130),
}

def material_assistant(instruction: str, material_name: str | None = None) -> dict[str, Any]:
    il = instruction.lower()
    # Match longest color name first (so "deep purple" beats "purple")
    matched_color = None
    for cname, rgb in sorted(COLOR_MAP.items(), key=lambda x: -len(x[0])):
        if cname in il:
            matched_color = (cname, rgb)
            break
    target_hint = next((w for w in ["fabric","wood","metal","marble","concrete","glass","leather",
                                     "wall","floor","ceiling","paint","plaster","tile","carpet",
                                     "stone","brick","curtain","sofa","cabinet","panel","door",
                                     "frame","shelf","unit","backdrop","niche","display"] if w in il), "")
    if matched_color:
        cname,(r,g,b) = matched_color
        mat_name = material_name or cname.replace(" ","_").title()
        return _ruby(f"""
        m=Sketchup.active_model; target={repr(target_hint)}; changed=[]
        mat=m.materials[{repr(mat_name)}]||m.materials.add({repr(mat_name)})
        mat.color=Sketchup::Color.new({r},{g},{b})
        m.start_operation("MCP Material Edit",true)
        m.materials.each{{|em| match=target.empty?||em.name.downcase.include?(target)
          if match; em.color=Sketchup::Color.new({r},{g},{b}); changed<<em.name; end}}
        def paint_named(entities,target,mat,count=0)
          entities.each{{|e|
            if e.is_a?(Sketchup::ComponentInstance) || e.is_a?(Sketchup::Group)
              if e.is_a?(Sketchup::ComponentInstance)
                n = e.definition.name.downcase
                ch = e.definition.entities
              else
                n = e.name.downcase
                ch = e.entities
              end
              if target.empty? || n.include?(target)
                ch.grep(Sketchup::Face).each {{|f| f.material = mat; count += 1}}
              end
              count = paint_named(ch, target, mat, count)
            end
          }}
          count
        end
        faces_painted=paint_named(m.entities,target,mat)
        m.commit_operation
        {{instruction:{repr(instruction)},material_name:{repr(mat_name)},color:"{cname}",rgb:[{r},{g},{b}],
         materials_changed:changed.count,changed_names:changed,faces_painted:faces_painted}}
        """)
    return _ruby(f"""
    m=Sketchup.active_model
    {{instruction:{repr(instruction)},materials_in_model:m.materials.map(&:name),
     note:"Could not parse a color. Specify a color name (e.g. purple, dark blue, warm white) and optionally a target component or material name.",
     status:"clarification_needed"}}
    """)

MATERIAL_PRESETS = {
    "polished marble":   (240,235,225,0.85,0.05,1.50,0.0,0.0),
    "travertine":        (210,195,170,0.40,0.30,1.45,0.0,0.0),
    "limestone":         (200,190,175,0.25,0.50,1.40,0.0,0.0),
    "concrete":          (150,148,145,0.10,0.80,1.30,0.0,0.0),
    "glass":             (200,230,240,0.90,0.00,1.52,0.0,0.95),
    "frosted glass":     (220,235,240,0.70,0.30,1.52,0.0,0.90),
    "frosted plexiglass":(230,240,245,0.65,0.25,1.49,0.0,0.85),
    "acrylic":           (240,240,245,0.75,0.05,1.49,0.0,0.85),
    "chrome":            (220,220,225,0.98,0.00,3.00,1.0,0.0),
    "polished chrome":   (220,220,225,0.98,0.00,3.00,1.0,0.0),
    "brushed aluminium": (180,185,190,0.85,0.20,3.00,1.0,0.0),
    "satin aluminium":   (175,180,185,0.80,0.15,3.00,1.0,0.0),
    "brass":             (180,150,80, 0.88,0.10,2.50,1.0,0.0),
    "brushed stainless": (190,190,192,0.90,0.18,2.80,1.0,0.0),
    "oak veneer":        (180,130,70, 0.15,0.70,1.45,0.0,0.0),
    "painted mdf":       (240,240,235,0.08,0.90,1.35,0.0,0.0),
    "velvet":            (80, 40, 90, 0.03,1.00,1.20,0.0,0.0),
    "leather":           (80, 55, 40, 0.12,0.60,1.40,0.0,0.0),
    "fabric":            (160,155,150,0.02,1.00,1.20,0.0,0.0),
    "ceramic":           (245,243,240,0.70,0.05,1.55,0.0,0.0),
}

def create_vray_material(description: str, material_name: str | None = None) -> dict[str, Any]:
    dl = description.lower()
    preset = matched_key = None
    for key, vals in MATERIAL_PRESETS.items():
        if all(w in dl for w in key.split()):
            preset, matched_key = vals, key; break
    if not preset:
        for key, vals in MATERIAL_PRESETS.items():
            if any(w in dl for w in key.split()):
                preset, matched_key = vals, key; break
    if not preset:
        preset, matched_key = (200,200,200,0.1,0.8,1.4,0.0,0.0), ""
    r,g,b,refl,rough,ior,metal,refr = preset
    name = material_name or description.replace(" ","_").title()
    return _ruby(f"""
    m=Sketchup.active_model
    mat=m.materials[{repr(name)}]||m.materials.add({repr(name)})
    mat.color=Sketchup::Color.new({r},{g},{b})
    mat.set_attribute("vray_props","reflection",{refl})
    mat.set_attribute("vray_props","roughness",{rough})
    mat.set_attribute("vray_props","ior",{ior})
    mat.set_attribute("vray_props","metalness",{metal})
    mat.set_attribute("vray_props","refraction",{refr})
    mat.set_attribute("vray_props","description",{repr(description)})
    {{name:mat.name,matched_preset:{repr(matched_key or "custom")},color_rgb:[{r},{g},{b}],
     reflection:{refl},roughness:{rough},ior:{ior},metalness:{metal},refraction:{refr},status:"created"}}
    """)

def texture_management(action: str) -> dict[str, Any]:
    return _ruby(f"""
    m=Sketchup.active_model; action={repr(action.lower())}
    missing=[]; dupes={{}}; all_tex=[]
    m.materials.each{{|mat| next unless mat.texture
      f=mat.texture.filename.to_s; all_tex<<{{material:mat.name,file:f}}
      missing<<{{material:mat.name,file:f}} if f.empty?||!File.exist?(f)}}
    files=all_tex.map{{|t|t[:file]}}
    files.each{{|f| c=files.count(f); dupes[f]=c if c>1&&!f.empty?}}
    {{action:action,total_textured_materials:all_tex.count,
     missing_textures:missing,duplicate_texture_files:dupes,status:"complete"}}
    """)

LIGHTING_RECS = {
    "soft":     "Reduce Sun multiplier to 0.5, increase HDRI, add large Rectangle fill light",
    "bright":   "Increase HDRI by 1 stop, add ceiling Rectangle lights at 2000-5000 lm",
    "showroom": "Neutral HDRI (overcast studio), 4 Rectangle lights at ceiling, disable Sun",
    "moody":    "Reduce HDRI to 0.3, warm rotation, reduce GI to 0.8, use warm point lights",
    "evening":  "Disable Sun/Sky, use warm sunset HDRI, add interior lamp lights",
    "interior": "Sun+Sky with low multiplier, Rectangle lights at windows for bounce fill",
    "overexpos":"Reduce camera EV by 1 stop or reduce HDRI multiplier by 50%",
    "too dark": "Increase HDRI intensity or add large area fill light above scene",
    "noisy":    "Increase light subdivisions, enable denoiser, raise noise threshold",
    "shadow":   "Add fill Rectangle light opposite key, set to 20-30% of key intensity",
}

def lighting_assistant(instruction: str) -> dict[str, Any]:
    il = instruction.lower()
    rec = next((r for k,r in LIGHTING_RECS.items() if k in il),
               "Describe the lighting issue for targeted recommendations.")
    scene_lights = _ruby("""
    m=Sketchup.active_model
    lights=m.entities.select{|e|e.is_a?(Sketchup::ComponentInstance)&&e.definition.name.to_s=~/light|vray|sun|sky|dome|ies/i}
           .map{|l|{name:l.definition.name,hidden:l.hidden?,layer:l.layer.name}}
    {lights:lights,total:lights.count}
    """)
    return {"instruction":instruction,"lights_in_scene":scene_lights.get("total",0),
            "light_list":scene_lights.get("lights",[]),"recommendation":rec,"status":"analysis_complete",
            "note":"Apply changes in V-Ray Asset Editor. V-Ray SDK required for automatic adjustments."}

DIAGNOSTICS = {
    "noisy":    ("Insufficient samples or light subdivisions.",
                 ["Raise noise threshold to 0.005","Enable V-Ray denoiser","Increase light subdivisions to 16+"]),
    "black":    ("Missing environment or incorrect IOR on reflective material.",
                 ["Assign HDRI environment","Check IOR > 1.0","Enable background visibility"]),
    "blurry":   ("Low texture resolution or incorrect UV mapping.",
                 ["Use 2K+ textures for close materials","Verify UV mapping","Disable texture filter override"]),
    "flat":     ("No GI or low GI contribution.",
                 ["Enable GI (Brute Force + Light Cache)","Increase GI multiplier to 1.0","Add ambient fill light"]),
    "overexpos":("Camera EV or HDRI too bright.",
                 ["Reduce camera EV by 1-2 stops","Reduce HDRI multiplier","Enable physical camera"]),
    "too dark": ("Insufficient lighting or GI disabled.",
                 ["Increase HDRI intensity","Add fill Rectangle light","Check GI is enabled"]),
    "missing":  ("Textures not found at stored paths.",
                 ["Run texture_management to locate missing textures","Relink textures","Pack model before moving files"]),
    "glass":    ("Incorrect glass material setup.",
                 ["Set IOR to 1.52","Enable refraction","Set reflection to 0.9+","Ensure background is visible"]),
}

def render_diagnostics(issue: str) -> dict[str, Any]:
    il = issue.lower()
    cause, recs = next(((c,r) for k,(c,r) in DIAGNOSTICS.items() if k in il),
                       ("Issue not matched to a known pattern.",
                        ["Share more render symptom details for a specific diagnosis."]))
    scene = _ruby("""
    m=Sketchup.active_model
    {faces:m.entities.grep(Sketchup::Face).count,materials:m.materials.count,
     reversed:m.entities.grep(Sketchup::Face).count{|f|f.normal.z<0}}
    """)
    return {"issue":issue,"likely_cause":cause,"recommendations":recs,
            "scene_faces":scene.get("faces"),"scene_materials":scene.get("materials"),
            "reversed_faces":scene.get("reversed"),"status":"diagnosis_complete"}

def generate_scene_report() -> dict[str, Any]:
    scene   = analyze_scene()
    texture = texture_management("report")
    issues, suggestions = [], []
    if scene.get("reversed_faces",0)>0:
        issues.append(f"{scene['reversed_faces']} reversed faces.")
        suggestions.append("Run prepare_scene_for_rendering with fix_reversed_faces=true.")
    if texture.get("missing_textures"):
        issues.append(f"{len(texture['missing_textures'])} missing textures.")
        suggestions.append("Run texture_management to relink missing textures.")
    if scene.get("duplicate_materials"):
        issues.append(f"Duplicate material names: {scene['duplicate_materials']}")
    if scene.get("total_faces",0)>500_000:
        issues.append(f"High poly count ({scene['total_faces']:,} faces).")
        suggestions.append("Use V-Ray proxies for heavy geometry.")
    return {
        "model_name":          scene.get("model_name"),
        "rendering_readiness": "needs_attention" if issues else "good",
        "scene_stats": {"faces":scene.get("total_faces"),"edges":scene.get("total_edges"),
                        "instances":scene.get("total_instances"),"materials":scene.get("materials_count"),
                        "tags":scene.get("tags_count"),"reversed_faces":scene.get("reversed_faces")},
        "issues":issues,"suggestions":suggestions,
        "texture_report":texture,"components":scene.get("components",[]),"tags":scene.get("tags",[]),
    }


# ---------------------------------------------------------------------------
# Environment & Camera tools
# ---------------------------------------------------------------------------

def get_environment_setup() -> dict[str, Any]:
    """Read environment, camera, sun and V-Ray settings — split into small calls to avoid timeouts."""
    # Call 1: camera + sun + sky
    base = _ruby("""
    m=Sketchup.active_model; view=m.active_view; cam=view.camera
    si=m.shadow_info; ro=m.rendering_options
    {
      camera: {perspective: cam.perspective?, fov: cam.fov.round(2),
               focal_length: cam.focal_length.round(2),
               image_width: view.vpwidth, image_height: view.vpheight,
               aspect_ratio: (view.vpwidth.to_f/view.vpheight).round(3)},
      sun: {display_shadows: si["DisplayShadows"], light_intensity: si["Light"],
            dark_intensity: si["Dark"], day_of_year: si["DayOfYear"],
            city: si["City"], country: si["Country"],
            latitude: si["Latitude"].to_f.round(4), longitude: si["Longitude"].to_f.round(4),
            north_angle: si["NorthAngle"].to_f.round(2), tz_offset: si["TZOffset"],
            use_sun_for_shading: si["UseSunForAllShading"]},
      sky: {background_color: ro["BackgroundColor"].to_s,
            fog_enabled: ro["DisplayFog"], sky_color: ro["SkyColor"].to_s},
      sketchup_version: Sketchup.version
    }
    """)

    # Call 2: scenes list
    scenes_data = _ruby("""
    m=Sketchup.active_model
    active=m.pages.selected_page
    m.pages.map{|p|
      {name: p.name, active: p==active,
       use_camera: p.use_camera?,
       use_shadow_info: p.use_shadow_info?,
       use_rendering_opts: p.use_rendering_options?}
    }
    """)

    # Call 3: V-Ray quick check
    vray_data = _ruby("""
    if defined?(VRay)
      begin
        sc=VRay::Scene.getActiveVRayScene rescue nil
        cn=sc ? (sc.physicalCamera rescue nil) : nil
        {available: true,
         camera: cn ? {
           exposure: (cn.exposure rescue nil),
           f_number: (cn.fNumber rescue nil),
           iso: (cn.ISO rescue nil),
           shutter_speed: (cn.shutterSpeed rescue nil),
           white_balance: (cn.whiteBalance rescue nil)
         } : nil}
      rescue => e
        {available: true, error: e.message}
      end
    else
      {available: false}
    end
    """)

    result = base if isinstance(base, dict) else {}
    result["scenes"] = scenes_data if isinstance(scenes_data, list) else []
    result["vray"]   = vray_data   if isinstance(vray_data, dict)  else {"available": False}
    return result



def save_environment_scene(scene_name: str) -> dict[str, Any]:
    """
    Create or update a SketchUp scene that saves the current camera,
    shadow, rendering options, and style — so the setup can always be restored.
    """
    return _ruby(f"""
    m    = Sketchup.active_model
    name = {repr(scene_name)}

    # Find existing scene or create new one
    page = m.pages[name]
    existed = !page.nil?

    m.start_operation("MCP Save Environment Scene", true)
    if page.nil?
      page = m.pages.add(name)
    end

    # Save all environment properties into this scene
    page.set_visibility(nil, false) rescue nil

    # Flags: camera + rendering options + shadow info + style
    flags = Sketchup::Page::CAMERA_POS |
            Sketchup::Page::RENDERING_OPTIONS |
            Sketchup::Page::SHADOWINFO |
            Sketchup::Page::SKETCHUP_PAGE_USE_STYLE rescue (1|4|8|16)

    # Update the scene to capture current settings
    m.pages.selected_page = page
    page.update(255) rescue nil

    m.commit_operation

    {{
      scene_name:  name,
      existed:     existed,
      action:      existed ? "updated" : "created",
      status:      "saved",
      note:        "Scene '#{{name}}' now stores camera, sun, shadows and rendering options. Click it anytime to restore."
    }}
    """)


def apply_environment_settings(settings: dict) -> dict[str, Any]:
    """
    Apply environment, sun, camera or V-Ray settings.
    settings keys: sun_light, sun_dark, shadow_time, fov, perspective,
                   fog_enabled, vray_exposure, vray_f_number, vray_iso,
                   vray_shutter, vray_white_balance
    """
    lines = []

    if "sun_light" in settings:
        v = float(settings["sun_light"])
        lines.append(f"si['Light'] = {v}")

    if "sun_dark" in settings:
        v = float(settings["sun_dark"])
        lines.append(f"si['Dark'] = {v}")

    if "display_shadows" in settings:
        v = "true" if settings["display_shadows"] else "false"
        lines.append(f"si['DisplayShadows'] = {v}")

    if "fov" in settings:
        v = float(settings["fov"])
        lines.append(f"cam.fov = {v}")

    if "perspective" in settings:
        v = "true" if settings["perspective"] else "false"
        lines.append(f"cam.perspective = {v}")

    if "fog_enabled" in settings:
        v = "true" if settings["fog_enabled"] else "false"
        lines.append(f"ro['DisplayFog'] = {v}")

    apply_block = "\n    ".join(lines) if lines else "# no sketchup settings"

    # V-Ray block — only runs if V-Ray is loaded
    vray_lines = []
    vray_cam_settings = {
        "vray_exposure":      "exposure",
        "vray_f_number":      "fNumber",
        "vray_iso":           "ISO",
        "vray_shutter":       "shutterSpeed",
        "vray_white_balance": "whiteBalance",
    }
    for key, vray_attr in vray_cam_settings.items():
        if key in settings:
            v = settings[key]
            vray_lines.append(f"cam_node.{vray_attr} = {repr(v)}")

    vray_block = "\n      ".join(vray_lines) if vray_lines else "# no vray camera settings"

    return _ruby(f"""
    m    = Sketchup.active_model
    view = m.active_view
    cam  = view.camera
    ro   = m.rendering_options
    si   = m.shadow_info
    changed = []

    m.start_operation("MCP Apply Environment", true)
    {apply_block}
    {"changed << 'sketchup_settings'" if lines else ""}
    m.commit_operation

    if defined?(VRay)
      begin
        vr_scene = VRay::Scene.getActiveVRayScene rescue nil
        if vr_scene
          cam_node = vr_scene.physicalCamera rescue nil
          if cam_node
            {vray_block}
            {"changed << 'vray_camera'" if vray_lines else ""}
          end
        end
      rescue => e
        # VRay error — non-fatal
      end
    end

    view.invalidate
    {{
      applied:  {repr(settings)},
      changed:  changed,
      status:   "ok"
    }}
    """)


def diagnose_environment() -> dict[str, Any]:
    """
    Diagnose common environment issues: overexposure, underexposure,
    sun/shadow misconfiguration, camera problems, V-Ray exposure issues.
    Returns issues list with severity and fix recommendations.
    """
    setup = get_environment_setup()

    issues = []
    recommendations = []

    sun = setup.get("sun", {})
    cam = setup.get("camera", {})
    vray = setup.get("vray", {})

    # Sun light intensity checks
    light = sun.get("light_intensity", 80)
    dark  = sun.get("dark_intensity", 0)

    if isinstance(light, (int, float)):
        if light > 90:
            issues.append({
                "type": "overexposure",
                "severity": "high",
                "detail": f"Sun light intensity is very high ({light}/100)",
                "fix": "Reduce sun light intensity to 70-80"
            })
            recommendations.append({"setting": "sun_light", "current": light, "suggested": 75})
        elif light < 40:
            issues.append({
                "type": "underexposure",
                "severity": "medium",
                "detail": f"Sun light intensity is low ({light}/100)",
                "fix": "Increase sun light intensity to 70-80"
            })
            recommendations.append({"setting": "sun_light", "current": light, "suggested": 75})

    if isinstance(dark, (int, float)) and dark > 60:
        issues.append({
            "type": "ambient_too_bright",
            "severity": "medium",
            "detail": f"Shadow (ambient) intensity is high ({dark}/100) — shadows will look washed out",
            "fix": "Reduce shadow intensity to 20-40 for more contrast"
        })
        recommendations.append({"setting": "sun_dark", "current": dark, "suggested": 30})

    # Camera FOV checks
    fov = cam.get("fov", 45)
    if isinstance(fov, (int, float)):
        if fov > 90:
            issues.append({
                "type": "wide_fov",
                "severity": "low",
                "detail": f"Camera FOV is very wide ({fov}°) — may cause distortion",
                "fix": "Use 45-60° for standard architectural views, 28-35mm equiv for interiors"
            })
        elif fov < 15:
            issues.append({
                "type": "narrow_fov",
                "severity": "low",
                "detail": f"Camera FOV is very narrow ({fov}°) — telephoto compression",
                "fix": "Increase FOV if this is not intentional"
            })

    # V-Ray camera checks
    if vray.get("available") and isinstance(vray.get("camera"), dict):
        vc = vray["camera"]
        exposure = vc.get("exposure")
        f_number = vc.get("f_number")
        iso      = vc.get("iso")

        if isinstance(exposure, (int, float)):
            if exposure > 1.5:
                issues.append({
                    "type": "vray_overexposure",
                    "severity": "high",
                    "detail": f"V-Ray exposure is high ({exposure}) — render will be blown out",
                    "fix": "Reduce V-Ray exposure to 0.5-1.0"
                })
                recommendations.append({"setting": "vray_exposure", "current": exposure, "suggested": 0.8})
            elif exposure < 0.2:
                issues.append({
                    "type": "vray_underexposure",
                    "severity": "high",
                    "detail": f"V-Ray exposure is very low ({exposure}) — render will be very dark",
                    "fix": "Increase V-Ray exposure to 0.5-1.0"
                })
                recommendations.append({"setting": "vray_exposure", "current": exposure, "suggested": 0.8})

        if isinstance(f_number, (int, float)) and f_number < 1.4:
            issues.append({
                "type": "vray_aperture_wide",
                "severity": "medium",
                "detail": f"V-Ray aperture f/{f_number} is very wide — deep DOF blur and overexposure risk",
                "fix": "Use f/5.6 to f/11 for architectural renders"
            })
            recommendations.append({"setting": "vray_f_number", "current": f_number, "suggested": 8.0})

    if not issues:
        issues.append({
            "type": "none",
            "severity": "ok",
            "detail": "No obvious environment issues detected",
            "fix": "Settings look reasonable"
        })

    return {
        "current_setup": setup,
        "issues": issues,
        "issue_count": len([i for i in issues if i["severity"] != "ok"]),
        "recommendations": recommendations,
        "vray_available": vray.get("available", False)
    }
