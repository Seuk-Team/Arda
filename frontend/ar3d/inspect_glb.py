# 아르 glb 구조 덤프 — 본·액션·키프레임·재질을 JSON 으로 찍는다.
# 모션을 고치기 전에 현재 값이 뭔지 확인하는 용도.
#
#   blender -b --python inspect_glb.py -- [<file.glb>] > dump.txt
#
# 인자를 생략하면 app/public/ar.glb 를 본다.
# 출력이 크므로(수십 KB) 파일로 받아서 필요한 액션만 골라 읽는 걸 권장.
import bpy, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_GLB = os.path.join(HERE, "..", "app", "public", "ar.glb")

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
glb_path = os.path.abspath(argv[0]) if argv else os.path.abspath(DEFAULT_GLB)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb_path)

out = {
    "file": glb_path,
    "objects": [],
    "actions": {},
    "materials": [m.name for m in bpy.data.materials],
    "images": [i.name for i in bpy.data.images],
}

arm = None
for o in bpy.data.objects:
    e = {"name": o.name, "type": o.type}
    if o.type == "ARMATURE":
        arm = o
        e["bones"] = [b.name for b in o.data.bones]
    if o.type == "MESH":
        e["dims"] = list(o.dimensions)
    out["objects"].append(e)


def fcurves_of(a):
    """Blender 4.4+ slotted action 경로"""
    for layer in a.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                yield from bag.fcurves


for a in bpy.data.actions:
    ch = {}
    for f in fcurves_of(a):
        ch[f"{f.data_path}[{f.array_index}]"] = [
            [round(k.co[0], 2), round(k.co[1], 4)] for k in f.keyframe_points
        ]
    out["actions"][a.name] = {"range": list(a.frame_range), "channels": ch}

if arm:
    out["rest"] = {
        b.name: {"head": [round(v, 3) for v in b.head_local],
                 "tail": [round(v, 3) for v in b.tail_local]}
        for b in arm.data.bones
    }

print("INSPECT_JSON_START")
print(json.dumps(out, ensure_ascii=False))
print("INSPECT_JSON_END")
