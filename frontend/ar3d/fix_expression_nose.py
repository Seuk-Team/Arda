# 표정이 바뀔 때 코 모양이 같이 바뀌던 문제를 고친다.
#
# 표정 세트(ExAsk·ExHappy·ExSad)는 저마다 얼굴 중앙에 자기 ExInk 코 마크를 들고 있어서,
# 표정이 켜지면 기본 코(초록 돌기, tripo_mat) 위에 다른 잉크 자국이 덧씌워졌다.
# 그 중앙 잉크만 지운다 — 눈(좌우 |x|>8)은 건드리지 않으므로 표정 자체는 그대로다.
#
#   blender -b --python fix_expression_nose.py -- [<in.glb>] [<out.glb>]
#
# 인자를 생략하면 app/public/ar.glb 를 제자리에서 갱신한다.
# 이미 지워진 파일에 다시 돌려도 안전하다(지울 게 없으면 그냥 통과).
import bpy, bmesh, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_GLB = os.path.join(HERE, "..", "app", "public", "ar.glb")

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
src = os.path.abspath(argv[0]) if len(argv) > 0 else os.path.abspath(DEFAULT_GLB)
dst = os.path.abspath(argv[1]) if len(argv) > 1 else src

EX_GROUPS = ("ExAsk", "ExHappy", "ExSad")
INK_MAT = "ExInk"      # 표정의 선(눈매·코) 재질
CENTER_X = 8.0         # |x| < 8 = 얼굴 중앙 = 코. 눈은 |x| 9~28 에 있다.

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)

obj = next(o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("Aru"))
me = obj.data
gidx = {g.name: g.index for g in obj.vertex_groups}
ex_indices = {gidx[n] for n in EX_GROUPS if n in gidx}

# 표정 본에 물린 정점
weighted = {
    v.index for v in me.vertices
    if any(g.group in ex_indices and g.weight > 0.01 for g in v.groups)
}

# 그중 ExInk 재질을 쓰면서 얼굴 중앙에 있는 것 = 표정별 코 마크
ink_slots = {i for i, m in enumerate(me.materials) if m and m.name == INK_MAT}
doomed = set()
for p in me.polygons:
    if p.material_index not in ink_slots:
        continue
    vs = list(p.vertices)
    if not all(v in weighted for v in vs):
        continue
    if all(abs(me.vertices[v].co.x) < CENTER_X for v in vs):
        doomed.update(vs)

print(f"표정 본 정점 {len(weighted)}, 지울 중앙 코 정점 {len(doomed)}")

if doomed:
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.verts[i] for i in doomed], context="VERTS")
    bm.to_mesh(me)
    bm.free()
    me.update()
    print("삭제 완료, 남은 정점", len(me.vertices))
else:
    print("지울 것 없음 — 이미 고쳐진 파일")

bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", export_animations=True)
print("EXPORTED:", dst)
