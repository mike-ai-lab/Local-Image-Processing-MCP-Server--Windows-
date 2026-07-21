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
