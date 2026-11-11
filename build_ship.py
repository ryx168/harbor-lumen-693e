# Procedural cinematic cruise scene for XO Tours #7622 -- the Majestic Princess
# at dawn off an Irish/British headland, for the 2027-03-29 Ireland & Britain
# 11-day cruise. Built entirely from Python in Blender 4.5: all geometry, every
# shader (node trees in code, no texture files), the lighting, camera and the
# compositor grade. No GPU, no image textures.
#
# Usage:  blender -b -P build_ship.py -- [preview|final|anim [png]] [tag]
# Env overrides (used by the GitHub Actions pipeline):
#   SHIP_ROOT     output root (default: the folder this script lives in)
#   SHIP_RES      resolution percentage, e.g. 100
#   SHIP_SAMPLES  Cycles samples
#   SHIP_FRAMES   "a-b" frame sub-range for anim mode (disables resume)
import bpy, bmesh, math, random, sys, os
from mathutils import Vector

ROOT = (os.environ.get('SHIP_ROOT') or os.path.dirname(os.path.abspath(__file__))).replace('\\', '/')
ARGS = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
MODE = "final" if "final" in ARGS else "preview"
TAG = ARGS[-1] if ARGS and ARGS[-1] not in ('preview', 'final', 'anim', 'png') else '01'
random.seed(7622)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
coll = bpy.context.collection

# ----------------------------------------------------------------- helpers
def mat_new(name):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    return m, nt, out

def node(nt, t, **props):
    n = nt.nodes.new(t)
    for k, v in props.items(): setattr(n, k, v)
    return n

def mesh_obj(name, bm, mat=None, loc=(0,0,0)):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); ob.location = loc
    coll.objects.link(ob)
    if mat: me.materials.append(mat)
    return ob

def smooth(ob):
    for p in ob.data.polygons: p.use_smooth = True

def box(name, center, dims, mat, rot=(0,0,0)):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts: v.co = Vector((v.co.x*dims[0], v.co.y*dims[1], v.co.z*dims[2]))
    ob = mesh_obj(name, bm, mat, center); ob.rotation_euler = rot
    return ob

def cyl(name, center, r, h, mat, segs=32, rot=(0,0,0), r2=None, caps=True):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=caps, segments=segs, radius1=r, radius2=(r if r2 is None else r2), depth=h)
    ob = mesh_obj(name, bm, mat, center); ob.rotation_euler = rot
    smooth(ob); return ob

def sphere(name, center, r, mat, rings=16, segs=24):
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=r)
    ob = mesh_obj(name, bm, mat, center); smooth(ob); return ob

def bevel(ob, width, segs=3):
    m = ob.modifiers.new('bevel', 'BEVEL'); m.width = width; m.segments = segs; m.limit_method = 'ANGLE'
    return m

def array_mod(ob, count, offset):
    m = ob.modifiers.new('arr', 'ARRAY'); m.count = count
    m.use_relative_offset = False; m.use_constant_offset = True; m.constant_offset_displace = offset

def text_obj(name, body, loc, rot, size, mat, extrude=0.02, align='CENTER'):
    cu = bpy.data.curves.new(name, 'FONT'); cu.body = body; cu.size = size; cu.extrude = extrude
    cu.align_x = align; cu.align_y = 'CENTER'
    if FONT: cu.font = FONT
    ob = bpy.data.objects.new(name, cu); ob.location = loc; ob.rotation_euler = rot
    coll.objects.link(ob); cu.materials.append(mat); return ob

def point_light(name, loc, energy, color, size=0.3):
    lt = bpy.data.lights.new(name, 'POINT'); lt.energy = energy; lt.color = color; lt.shadow_soft_size = size
    lo = bpy.data.objects.new(name, lt); lo.location = loc; coll.objects.link(lo); return lo

FONT = None
for fp in ["C:/Windows/Fonts/arialbd.ttf",
           "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
           "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
    if os.path.exists(fp):
        try: FONT = bpy.data.fonts.load(fp); break
        except Exception: pass

# ----------------------------------------------------------------- shader helpers (all code)
def principled(nt, out, **kw):
    p = node(nt, 'ShaderNodeBsdfPrincipled')
    for k, v in kw.items():
        if k in p.inputs: p.inputs[k].default_value = v
    nt.links.new(p.outputs[0], out.inputs['Surface']); return p

def coords(nt, which='Generated'):
    tc = node(nt, 'ShaderNodeTexCoord'); return tc.outputs[which]

def mixcol(nt, fac, a, b, blend='MIX'):
    m = node(nt, 'ShaderNodeMix', data_type='RGBA', blend_type=blend)
    if hasattr(fac, 'links'): nt.links.new(fac, m.inputs[0])
    else: m.inputs[0].default_value = fac
    for sock, val in ((6, a), (7, b)):
        if hasattr(val, 'links'): nt.links.new(val, m.inputs[sock])
        else: m.inputs[sock].default_value = val
    return m.outputs[2]

def ramp(nt, fac, stops):
    r = node(nt, 'ShaderNodeValToRGB')
    el = r.color_ramp.elements
    while len(el) > 1: el.remove(el[-1])
    el[0].position = stops[0][0]; el[0].color = stops[0][1]
    for pos, col in stops[1:]:
        e = el.new(pos); e.color = col
    nt.links.new(fac, r.inputs['Fac']); return r

def noise(nt, vec, scale, detail=2.0, rough=0.5, dist=0.0):
    n = node(nt, 'ShaderNodeTexNoise'); n.inputs['Scale'].default_value = scale
    n.inputs['Detail'].default_value = detail; n.inputs['Roughness'].default_value = rough
    n.inputs['Distortion'].default_value = dist
    nt.links.new(vec, n.inputs['Vector']); return n

def wave(nt, vec, scale, distortion=1.0, detail=2.0):
    w = node(nt, 'ShaderNodeTexWave'); w.inputs['Scale'].default_value = scale
    w.inputs['Distortion'].default_value = distortion; w.inputs['Detail'].default_value = detail
    nt.links.new(vec, w.inputs['Vector']); return w

def bump(nt, height, strength, p, dist=0.05):
    b = node(nt, 'ShaderNodeBump'); b.inputs['Strength'].default_value = strength; b.inputs['Distance'].default_value = dist
    nt.links.new(height, b.inputs['Height']); nt.links.new(b.outputs[0], p.inputs['Normal']); return b

def mat_simple(name, color, rough=0.5, metal=0.0, coat=0.0):
    m, nt, out = mat_new(name)
    principled(nt, out, **{'Base Color': color, 'Roughness': rough, 'Metallic': metal, 'Coat Weight': coat})
    return m

def mat_emission(name, color, strength):
    m, nt, out = mat_new(name)
    e = node(nt, 'ShaderNodeEmission'); e.inputs['Color'].default_value = color; e.inputs['Strength'].default_value = strength
    nt.links.new(e.outputs[0], out.inputs['Surface']); return m

# ----------------------------------------------------------------- sea
def mat_sea():
    m, nt, out = mat_new('sea')
    gen = coords(nt, 'Object')
    w1 = wave(nt, gen, 2.2, 6.0, 3.0)
    w2 = noise(nt, gen, 6.0, 6.0, 0.6, 1.4)
    h = node(nt, 'ShaderNodeMath', operation='ADD')
    nt.links.new(w1.outputs['Fac'], h.inputs[0]); nt.links.new(w2.outputs['Fac'], h.inputs[1])
    # deep dawn sea: cold blue-green, a warm sun-strip comes from the sky reflection
    p = principled(nt, out, **{'Base Color': (0.015, 0.045, 0.07, 1), 'Roughness': 0.08,
                               'Metallic': 0.0, 'IOR': 1.33, 'Transmission Weight': 0.0})
    p.inputs['Specular IOR Level'].default_value = 1.0
    bump(nt, h.outputs[0], 0.18, p, 0.12)
    return m

def mat_foam(name):
    m, nt, out = mat_new(name)
    e = node(nt, 'ShaderNodeEmission'); e.inputs['Color'].default_value = (0.8, 0.88, 0.95, 1); e.inputs['Strength'].default_value = 0.6
    tr = node(nt, 'ShaderNodeBsdfTransparent')
    gen = coords(nt, 'Object')
    n = noise(nt, gen, 14.0, 5.0, 0.7)
    r = ramp(nt, n.outputs['Fac'], [(0.45, (0,0,0,1)), (0.62, (1,1,1,1))])
    mx = node(nt, 'ShaderNodeMixShader')
    nt.links.new(r.outputs['Color'], mx.inputs[0])
    nt.links.new(tr.outputs[0], mx.inputs[1]); nt.links.new(e.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs['Surface'])
    return m

# ----------------------------------------------------------------- lit cabin windows
def mat_windows():
    # A warm window grid: Brick texture mortar = hull plate, bricks = cabins.
    # A second noise turns a fraction of the cabins dark so the band reads as
    # real lit windows at dawn rather than a glowing stripe.
    m, nt, out = mat_new('windows')
    gen = coords(nt, 'Object')
    map_ = node(nt, 'ShaderNodeMapping'); map_.inputs['Scale'].default_value = (34.0, 5.0, 1.0)
    nt.links.new(gen, map_.inputs['Vector'])
    br = node(nt, 'ShaderNodeTexBrick')
    br.inputs['Scale'].default_value = 1.0
    br.inputs['Mortar Size'].default_value = 0.06
    br.offset = 0.0; br.squash = 1.0
    br.inputs['Color1'].default_value = (1.0, 0.82, 0.5, 1)   # warm lit cabin
    br.inputs['Color2'].default_value = (1.0, 0.86, 0.6, 1)
    br.inputs['Mortar'].default_value = (0.05, 0.06, 0.08, 1) # dark frame
    nt.links.new(map_.outputs['Vector'], br.inputs['Vector'])
    # which cabins are lit
    lit = noise(nt, gen, 9.0, 2.0, 0.6)
    litr = ramp(nt, lit.outputs['Fac'], [(0.35, (0,0,0,1)), (0.5, (1,1,1,1))])
    e = node(nt, 'ShaderNodeEmission')
    nt.links.new(br.outputs['Color'], e.inputs['Color'])
    strength = node(nt, 'ShaderNodeMath', operation='MULTIPLY')
    nt.links.new(br.outputs['Fac'], strength.inputs[0])   # 0 at mortar, 1 at cabin
    nt.links.new(litr.outputs['Color'], strength.inputs[1])
    s2 = node(nt, 'ShaderNodeMath', operation='MULTIPLY'); s2.inputs[1].default_value = 5.0
    nt.links.new(strength.outputs[0], s2.inputs[0])
    nt.links.new(s2.outputs[0], e.inputs['Strength'])
    # dark glass where unlit
    glass = principled(nt, out, **{'Base Color': (0.02, 0.03, 0.05, 1), 'Roughness': 0.1, 'Metallic': 0.6})
    mx = node(nt, 'ShaderNodeMixShader')
    nt.links.new(strength.outputs[0], mx.inputs[0])
    nt.links.new(out.inputs['Surface'].links[0].from_socket, mx.inputs[1])
    nt.links.new(e.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs['Surface'])
    return m

# ----------------------------------------------------------------- headland + grass + rock
def mat_cliff():
    m, nt, out = mat_new('cliff')
    gen = coords(nt, 'Object')
    nz = noise(nt, gen, 1.4, 6.0, 0.7, 0.4)
    # green turf up top, grey rock on the steep sea face (driven by world Z of the mesh)
    sep = node(nt, 'ShaderNodeSeparateXYZ'); nt.links.new(gen, sep.inputs[0])
    band = node(nt, 'ShaderNodeMath', operation='MULTIPLY_ADD')
    nt.links.new(sep.outputs['Z'], band.inputs[0]); band.inputs[1].default_value = 1.2; band.inputs[2].default_value = 0.1
    grass = ramp(nt, nz.outputs['Fac'], [(0.3, (0.05, 0.14, 0.04, 1)), (0.7, (0.10, 0.24, 0.07, 1))])
    rock = ramp(nt, nz.outputs['Fac'], [(0.3, (0.14, 0.13, 0.12, 1)), (0.7, (0.26, 0.24, 0.22, 1))])
    mixed = mixcol(nt, band.outputs[0], rock.outputs['Color'], grass.outputs['Color'])
    p = principled(nt, out, **{'Roughness': 0.9})
    nt.links.new(mixed, p.inputs['Base Color'])
    bump(nt, nz.outputs['Fac'], 0.3, p, 0.25)
    return m

def headland():
    # a low, long landmass off the starboard bow; displaced plane pushed up.
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=48, y_segments=48, size=1.0)
    for v in bm.verts:
        x, y = v.co.x, v.co.y
        # radial falloff so edges meet the sea
        r = math.hypot(x, y)
        fall = max(0.0, 1.0 - r)
        h = 0.0
        h += math.sin(x*5.0)*math.cos(y*4.0)*0.12
        h += math.sin(x*11.0+1.3)*0.05
        h += random.uniform(-0.03, 0.03)
        base = (fall ** 1.6)
        v.co.z = (base + h*base) * 1.0
    me = bpy.data.meshes.new('headland'); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new('headland', me)
    ob.scale = (140, 110, 46)
    ob.location = (240, 150, -2)
    coll.objects.link(ob); me.materials.append(mat_cliff())
    for p in me.polygons: p.use_smooth = True
    return ob

# ----------------------------------------------------------------- lighthouse
def lighthouse(x, y, zbase):
    white = mat_simple('lh_white', (0.9, 0.9, 0.88, 1), 0.5)
    red = mat_simple('lh_red', (0.6, 0.08, 0.06, 1), 0.5)
    dark = mat_simple('lh_dark', (0.03, 0.03, 0.04, 1), 0.4, 0.3)
    glow = mat_emission('lh_lamp', (1.0, 0.92, 0.6, 1), 60.0)
    g = []
    g.append(cyl('lh_tower', (x, y, zbase+9), 2.4, 18, white, r2=1.7))
    g.append(cyl('lh_band1', (x, y, zbase+6), 1.95, 2.2, red))
    g.append(cyl('lh_band2', (x, y, zbase+12), 1.85, 2.2, red))
    g.append(cyl('lh_gallery', (x, y, zbase+18.1), 2.3, 0.6, dark))
    g.append(cyl('lh_lantern', (x, y, zbase+19.6), 1.5, 2.4, glow, segs=16))
    g.append(cyl('lh_cap', (x, y, zbase+21.2), 1.7, 0.9, dark, r2=0.1, segs=16))
    # keeper's cottage
    box('lh_house', (x+6, y+1, zbase+1.6), (5, 4, 3.2), white)
    box('lh_roof', (x+6, y+1, zbase+3.7), (5.4, 4.4, 1.2), red, rot=(0,0,0))
    point_light('lh_beam', (x, y, zbase+19.6), 1800, (1.0, 0.92, 0.65), size=1.2)
    return g

# ----------------------------------------------------------------- the ship
SHIP = None
def ship():
    global SHIP
    root = bpy.data.objects.new('ship_root', None); coll.objects.link(root)
    hull_white = mat_simple('hull_white', (0.86, 0.87, 0.86, 1), 0.35, coat=0.3)
    super_white = mat_simple('super_white', (0.90, 0.91, 0.90, 1), 0.4, coat=0.2)
    boot = mat_simple('boot_stripe', (0.04, 0.09, 0.22, 1), 0.4)     # navy boot-top
    waterline = mat_simple('waterline', (0.05, 0.08, 0.17, 1), 0.45) # navy hull band at the waterline
    dark = mat_simple('deck_dark', (0.06, 0.07, 0.09, 1), 0.6)
    gold = mat_simple('gold', (0.75, 0.55, 0.16, 1), 0.3, 0.9)
    funnel_blue = mat_simple('funnel_blue', (0.05, 0.16, 0.40, 1), 0.35, coat=0.3)
    glass = mat_simple('bridge_glass', (0.03, 0.05, 0.08, 1), 0.08, 0.7)
    orange = mat_simple('lifeboat', (0.85, 0.35, 0.05, 1), 0.5)
    wmat = mat_windows()

    parts = []
    L = 118.0
    # --- hull: a long box, bow (+X) and stern (-X) tapered via bmesh
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x*L, v.co.y*20.0, v.co.z*11.0))
    for v in bm.verts:
        fx = v.co.x / (L/2)
        if fx > 0.55:                      # bow: pinch the sides to a stem
            t = (fx-0.55)/0.45
            v.co.y *= (1 - 0.9*t)
            v.co.x += 4.0*t
        elif fx < -0.6:                    # stern: slight taper + transom
            t = (-fx-0.6)/0.4
            v.co.y *= (1 - 0.25*t)
        if v.co.z < 0:                     # give the keel a little deadrise
            v.co.y *= 0.82
    hull = mesh_obj('hull', bm, hull_white, (0, 0, 3.5))
    bevel(hull, 0.4, 2)
    parts.append(hull)
    # boot stripe + red underbody as thin proud bands on the hull side
    boot_b = box('boot', (2, 0, 7.9), (L*0.99, 20.4, 0.5), boot); parts.append(boot_b)
    red_b = box('underbody', (0, 0, 1.2), (L*0.9, 20.6, 2.2), waterline); parts.append(red_b)
    # name on the bow, port side (faces -Y, toward camera)
    # (pi/2,0,0): faces -Y (port), up +Z, reading runs world +X = screen-right for
    # a camera on the -Y side, so the name reads correctly without any scale flip.
    text_obj('ship_name', 'MAJESTIC PRINCESS', (34, -10.28, 6.2),
             (math.radians(90), 0, 0), 1.6, dark)

    # --- superstructure: a nearly solid white block of cabin decks that only
    # tapers near the top, each with a lit window band. The lower decks run
    # almost the full hull length so the ship reads as a liner, not a ziggurat.
    decks = 9
    base_z = 9.0
    dh = 3.2
    for i in range(decks):
        z = base_z + i*dh
        dl = L*0.95 - i*1.2      # only a gentle taper, so the decks read as one white hull
        dw = 19.4 - i*0.16
        if dl < 24: break
        cx = -1.0 - i*0.5
        d = box(f'deck_{i}', (cx, 0, z+dh/2), (dl, dw, dh), super_white)
        parts.append(d)
        # one slim lit cabin-window row high on each deck, slightly proud of the white wall
        wb = box(f'win_{i}', (cx, -dw/2-0.05, z+dh*0.62), (dl*0.97, 0.06, 0.95), wmat)
        parts.append(wb)

    top_z = base_z + decks*dh
    # --- sun deck clutter: domes (pool canopy), bridge, mast, funnel
    sphere('dome1', (18, 0, top_z+0.5), 3.0, super_white, rings=10, segs=20)
    sphere('dome2', (26, 0, top_z+0.3), 2.2, glass, rings=10, segs=20)
    # bridge wings up front
    box('bridge', (40, 0, base_z+decks*2.7-3.0), (10, 20.5, 2.4), super_white)
    box('bridge_glass', (41.2, -10.4, base_z+decks*2.7-3.0), (8, 0.1, 1.4), glass)
    # funnel aft: a big rounded blue stack with a gold band (Princess-style)
    fx = -30
    fn = box('funnel', (fx, 0, top_z+5.5), (9, 10, 12), funnel_blue)
    bevel(fn, 1.6, 4)
    box('funnel_band', (fx, 0, top_z+9.6), (9.3, 10.3, 1.1), gold)
    box('funnel_wing_l', (fx, 6.2, top_z+4.5), (7, 1.2, 9), funnel_blue)
    box('funnel_wing_r', (fx, -6.2, top_z+4.5), (7, 1.2, 9), funnel_blue)
    # radar mast on the bridge
    cyl('mast', (42, 0, base_z+decks*2.7+3.0), 0.25, 7, dark, segs=10)
    box('yard', (42, 0, base_z+decks*2.7+5.0), (0.2, 5, 0.2), dark)
    point_light('mast_lamp', (42, 0, base_z+decks*2.7+6.6), 40, (0.9,0.1,0.08), 0.15)

    # --- lifeboats along the promenade, port side, via array
    lb = cyl('lifeboat', (34, -9.6, base_z+3.2), 1.0, 3.6, orange, segs=12, rot=(0, math.radians(90), 0))
    bevel(lb, 0.5, 3)
    array_mod(lb, 12, (-6.0, 0, 0))
    parts.append(lb)

    # --- warm glow sources so the lit decks cast real light on the water/mist
    point_light('ship_glow1', (10, -12, 20), 500, (1.0, 0.7, 0.4), 4.0)
    point_light('ship_glow2', (-20, -12, 16), 400, (1.0, 0.72, 0.42), 4.0)

    for ob in list(coll.objects):
        if ob.parent is None and ob is not root and ob.type in ('MESH','FONT') and (
           ob.name.startswith(('hull','boot','underbody','ship_name','deck_','win_','edge_',
           'dome','bridge','funnel','mast','yard','lifeboat'))):
            ob.parent = root
    SHIP = root
    return root

# ----------------------------------------------------------------- build the scene
sea = None
def build():
    global sea
    # sea
    bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=2, y_segments=2, size=1.0)
    for v in bm.verts: v.co = Vector((v.co.x*3000, v.co.y*3000, 0))
    sea = mesh_obj('sea', bm, mat_sea(), (0, 400, 0))
    # faint wake behind the ship
    wk = box('wake', (-70, -2, 0.05), (90, 7, 0.02), mat_foam('wake'))
    headland()
    lighthouse(250, 90, 20)
    # a distant second rock stack
    sphere('rock', (300, 30, 1), 7, mat_simple('rock', (0.12,0.12,0.11,1), 0.9), rings=8, segs=12)
    ship()

build()

# ----------------------------------------------------------------- lighting / world / camera
world = bpy.data.worlds.new('World'); scene.world = world; world.use_nodes = True
wn = world.node_tree; wn.nodes.clear()
wout = wn.nodes.new('ShaderNodeOutputWorld')
sky = wn.nodes.new('ShaderNodeTexSky'); sky.sky_type = 'NISHITA'; sky.sun_disc = True
# sun to the right and toward the camera so the ship's visible port side is lit
SUN_AZ, SUN_EL = 55.0, 9.0
sky.sun_elevation = math.radians(SUN_EL); sky.sun_rotation = math.radians(SUN_AZ)
sky.dust_density = 1.8; sky.air_density = 1.3; sky.ozone_density = 1.5
try: sky.sun_intensity = 1.1
except Exception: pass
bg = wn.nodes.new('ShaderNodeBackground'); bg.inputs['Strength'].default_value = 1.8
wn.links.new(sky.outputs[0], bg.inputs['Color']); wn.links.new(bg.outputs[0], wout.inputs['Surface'])
# NO world volume: a world volume fills this whole 3000-unit exterior, and with
# volume_bounces=0 it extinguishes the (infinite-path) sun and the sky background
# -- it turns the entire frame black. Aerial depth comes from the Nishita sky's
# own atmosphere instead. (Opt in with SHIP_VOL only for a contained test.)
vol = wn.nodes.new('ShaderNodeVolumeScatter'); vol.inputs['Density'].default_value = 0.00008
vol.inputs['Anisotropy'].default_value = 0.6; vol.inputs['Color'].default_value = (0.95, 0.95, 1.0, 1)
if os.environ.get('SHIP_VOL'):
    wn.links.new(vol.outputs[0], wout.inputs['Volume'])

# key sun, matched to the sky's sun, low and warm, modelling the white decks
sun = bpy.data.lights.new('sun', 'SUN'); sun.energy = 7.0; sun.color = (1.0, 0.72, 0.46); sun.angle = math.radians(1.5)
so = bpy.data.objects.new('sun', sun)
so.rotation_euler = (math.radians(-(90-SUN_EL)), 0, math.radians(SUN_AZ)); coll.objects.link(so)
# cool sky fill from the opposite side so the shadowed hull is not pure black
fill = bpy.data.lights.new('fill', 'SUN'); fill.energy = 1.6; fill.color = (0.5, 0.62, 0.85); fill.angle = math.radians(8)
fo = bpy.data.objects.new('fill', fill)
fo.rotation_euler = (math.radians(-55), 0, math.radians(-120)); coll.objects.link(fo)

# a 3/4 bow beauty angle off the lit port side; a Track-To keeps it aimed
tgt = bpy.data.objects.new('cam_target', None); tgt.location = (-4, 0, 15); coll.objects.link(tgt)
cam_d = bpy.data.cameras.new('cam'); cam_d.lens = 45; cam_d.sensor_width = 36
cam_d.dof.use_dof = True; cam_d.dof.focus_distance = 205; cam_d.dof.aperture_fstop = 4.5
cam = bpy.data.objects.new('cam', cam_d); cam.location = (86, -192, 12)
coll.objects.link(cam); scene.camera = cam
tc = cam.constraints.new('TRACK_TO'); tc.target = tgt; tc.track_axis = 'TRACK_NEGATIVE_Z'; tc.up_axis = 'UP_Y'

# ----------------------------------------------------------------- render settings
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
if MODE == 'final':
    scene.render.resolution_percentage = 100; scene.cycles.samples = 320
else:
    scene.render.resolution_percentage = 50; scene.cycles.samples = 64
scene.cycles.use_adaptive_sampling = True; scene.cycles.adaptive_threshold = 0.02
scene.cycles.use_denoising = True; scene.cycles.denoiser = 'OPENIMAGEDENOISE'
scene.cycles.max_bounces = 8; scene.cycles.diffuse_bounces = 3; scene.cycles.glossy_bounces = 4
scene.cycles.transmission_bounces = 6; scene.cycles.volume_bounces = 0; scene.cycles.transparent_max_bounces = 8
scene.cycles.caustics_reflective = False; scene.cycles.caustics_refractive = False
scene.cycles.sample_clamp_indirect = 8.0; scene.cycles.blur_glossy = 1.0
scene.cycles.volume_step_rate = 1.0; scene.cycles.volume_max_steps = 256
scene.view_settings.view_transform = 'AgX'; scene.view_settings.look = 'AgX - Medium High Contrast'
scene.view_settings.exposure = 0.3
scene.render.image_settings.file_format = 'PNG'; scene.render.image_settings.color_depth = '16'

# compositor: bloom, subtle chromatic aberration, colour grade, vignette
if os.environ.get('SHIP_NOCOMP'):
    scene.use_nodes = False
else:
    scene.use_nodes = True; ct = scene.node_tree; ct.nodes.clear()
    rl = ct.nodes.new('CompositorNodeRLayers'); comp = ct.nodes.new('CompositorNodeComposite')
    glare = ct.nodes.new('CompositorNodeGlare')
    try: glare.glare_type = 'BLOOM'
    except Exception: glare.glare_type = 'FOG_GLOW'
    for attr, val in (('threshold', 1.0), ('mix', -0.5), ('size', 8), ('quality', 'HIGH')):
        try: setattr(glare, attr, val)
        except Exception: pass
    for sock, val in (('Threshold', 1.0), ('Strength', 0.22), ('Size', 0.7)):
        if sock in glare.inputs:
            try: glare.inputs[sock].default_value = val
            except Exception: pass
    cb = ct.nodes.new('CompositorNodeColorBalance'); cb.correction_method = 'LIFT_GAMMA_GAIN'
    cb.lift = (0.98, 0.99, 1.04); cb.gamma = (1.0, 1.0, 1.0); cb.gain = (1.08, 1.0, 0.92)
    ld = ct.nodes.new('CompositorNodeLensdist'); ld.inputs['Dispersion'].default_value = 0.012
    em = ct.nodes.new('CompositorNodeEllipseMask'); em.width = 1.5; em.height = 1.3
    bl = ct.nodes.new('CompositorNodeBlur'); bl.filter_type = 'FAST_GAUSS'; bl.size_x = 400; bl.size_y = 400; bl.use_relative = False
    mr = ct.nodes.new('CompositorNodeMapRange'); mr.inputs['From Min'].default_value = 0; mr.inputs['From Max'].default_value = 1
    mr.inputs['To Min'].default_value = 0.5; mr.inputs['To Max'].default_value = 1.0
    mul = ct.nodes.new('CompositorNodeMixRGB'); mul.blend_type = 'MULTIPLY'
    ct.links.new(rl.outputs['Image'], glare.inputs['Image'])
    ct.links.new(glare.outputs['Image'], cb.inputs['Image'])
    ct.links.new(cb.outputs['Image'], ld.inputs['Image'])
    ct.links.new(em.outputs['Mask'], bl.inputs['Image']); ct.links.new(bl.outputs['Image'], mr.inputs['Value'])
    ct.links.new(ld.outputs['Image'], mul.inputs[1]); ct.links.new(mr.outputs['Value'], mul.inputs[2])
    ct.links.new(mul.outputs['Image'], comp.inputs['Image'])

# ----------------------------------------------------------------- save + render
os.makedirs(ROOT + '/renders', exist_ok=True)
if "anim" in ARGS:
    # 4 s slow truck across the water: parallax between ship and the headland
    F0, F1 = 1, 96
    scene.frame_start, scene.frame_end = F0, F1; scene.render.fps = 24
    cam.location = (168, -150, 13); cam.keyframe_insert('location', frame=F0)
    cam.location = (96, -182, 18); cam.keyframe_insert('location', frame=F1)
    SHIP.location = (0, 0, 0.0); SHIP.keyframe_insert('location', frame=F0)
    SHIP.location = (0, 0, 0.4); SHIP.keyframe_insert('location', frame=48)
    SHIP.location = (0, 0, 0.0); SHIP.keyframe_insert('location', frame=F1)
    for ob in (cam, SHIP):
        if ob.animation_data and ob.animation_data.action:
            for fc in ob.animation_data.action.fcurves:
                for kp in fc.keyframe_points: kp.interpolation = 'SINE'
    scene.render.resolution_percentage = 50; scene.cycles.samples = 40
    if 'png' in ARGS:
        scene.render.image_settings.file_format = 'PNG'; scene.render.image_settings.color_depth = '8'
        os.makedirs(f'{ROOT}/renders/fly_{TAG}', exist_ok=True)
        scene.render.filepath = f'{ROOT}/renders/fly_{TAG}/f_'
        if os.environ.get('SHIP_FRAMES'):
            a, b = os.environ['SHIP_FRAMES'].split('-'); scene.frame_start, scene.frame_end = int(a), int(b)
            print('FRAME RANGE', scene.frame_start, scene.frame_end)
        else:
            done = sorted(int(f[2:6]) for f in os.listdir(f'{ROOT}/renders/fly_{TAG}') if f.startswith('f_') and f.endswith('.png'))
            if done:
                scene.frame_start = max(F0, max(done) + 1); print('RESUME from frame', scene.frame_start)
    else:
        scene.render.image_settings.file_format = 'FFMPEG'; scene.render.image_settings.color_depth = '8'
        scene.render.ffmpeg.format = 'MPEG4'; scene.render.ffmpeg.codec = 'H264'; scene.render.ffmpeg.constant_rate_factor = 'HIGH'
        scene.render.filepath = f'{ROOT}/renders/flythrough_{TAG}_'
    if os.environ.get('SHIP_RES'): scene.render.resolution_percentage = int(os.environ['SHIP_RES'])
    if os.environ.get('SHIP_SAMPLES'): scene.cycles.samples = int(os.environ['SHIP_SAMPLES'])
    bpy.ops.wm.save_as_mainfile(filepath=ROOT + '/ship_anim.blend')
    bpy.ops.render.render(animation=True)
    print('RENDERED ANIMATION', scene.render.filepath)
else:
    if os.environ.get('SHIP_RES'): scene.render.resolution_percentage = int(os.environ['SHIP_RES'])
    if os.environ.get('SHIP_SAMPLES'): scene.cycles.samples = int(os.environ['SHIP_SAMPLES'])
    bpy.ops.wm.save_as_mainfile(filepath=ROOT + '/ship.blend')
    scene.render.filepath = f'{ROOT}/renders/{MODE}_{TAG}.png'
    bpy.ops.render.render(write_still=True)
    print('RENDERED', scene.render.filepath, 'objects:', len(bpy.data.objects))
