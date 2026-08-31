# 감은 눈(confirm·fail) 에서 눈 둘레에 어색한 원이 보이던 문제를 고친다.
#
# 감은 눈은 얼굴에 ExLid 덮개를 씌워 텍스처에 그려진 눈을 가리는 방식인데,
# 그 덮개가 원반처럼 도드라져 보인 원인이 셋이었다:
#   (1) 색 — 얼굴은 [텍스처 × baseColorFactor] 라 실제 (0.456,0.543,0.277) 인데 덮개는 (0.284,0.417,0.098)
#   (2) 재질 — 얼굴 roughness 0.5 vs 덮개 1.0
#   (3) 형태 — 덮개가 얼굴 앞으로 볼록 튀어나와 단차(경계선)가 생겼다. (1)(2)만 고쳐도 원이 남는다
#
# 셋 다 맞춘다. (3) 은 덮개를 얼굴 곡면에 밀착시켜 없앤다:
#   - 돔의 뒤쪽 절반(얼굴 안쪽으로 들어간 부분)을 지운다. 남기면 앞뒤가 같은 x·z 를 공유해
#     밀착 시 자기 자신과 겹쳐 접히고 검은 얼룩이 생긴다(실험으로 확인)
#   - 남은 앞쪽 껍데기를 얼굴 표면 바로 앞(OFFSET)에 붙인다. x·z 범위는 그대로라 눈 가리는 면적은 유지된다
#   - 법선을 얼굴의 부드러운 정점 법선으로 덮어써 음영까지 얼굴과 같게 만든다
#     (레이캐스트가 주는 면 법선을 쓰면 각지고 일부는 뒤를 향해 검게 나온다)
#
#   blender -b --python fix_eye_lid.py -- [<in.glb>] [<out.glb>]
#
# 인자를 생략하면 app/public/ar.glb 를 제자리에서 갱신한다.
# 뒤쪽 절반은 한 번 지워지면 없고 남은 껍데기는 절대 위치(얼굴 앞 OFFSET)로 놓이므로,
# 여러 번 돌려도 결과가 같다.
import bpy, bmesh, os, sys
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_GLB = os.path.join(HERE, "..", "app", "public", "ar.glb")

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
src = os.path.abspath(argv[0]) if len(argv) > 0 else os.path.abspath(DEFAULT_GLB)
dst = os.path.abspath(argv[1]) if len(argv) > 1 else src

LID_MAT = "ExLid"
OFFSET = 1.0        # 덮개가 얼굴 표면보다 앞에 뜨는 정도.
                    # 0.25 까지 붙이면 텍스처에 그려진 눈이 얼룩덜룩 비친다 —
                    # 재질을 전부 불투명으로 바꿔도 그대로라 알파가 아니라 기하 문제다.
                    # 1.0 이 아티팩트 없이 단차가 가장 덜 보이는 값(실측).
KEEP_BACK = -0.5    # 얼굴 표면보다 이보다 더 뒤로 들어간 정점은 지운다 (돔의 뒤쪽 절반)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)

obj = next(o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("Aru"))
me = obj.data


def principled(mat):
    if not (mat and mat.use_nodes):
        return None
    return next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)


def slots(pred):
    return {i for i, m in enumerate(me.materials) if m and pred(m.name)}


def face_surface_bvh():
    """얼굴 폴리곤만으로 BVH — 덮개 자신에 레이가 맞지 않게"""
    return BVHTree.FromPolygons(
        [tuple(v.co) for v in me.vertices],
        [list(p.vertices) for p in me.polygons if p.material_index in slots(lambda n: n.startswith("tripo"))],
        all_triangles=False,
    )


def surface_y_of(vi):
    """정점의 x·z 위치에서 얼굴 앞면 y (없으면 None)"""
    co = me.vertices[vi].co
    loc, _, _, _ = bvh.ray_cast(Vector((co.x, -500.0, co.z)), Vector((0.0, 1.0, 0.0)))
    return None if loc is None else loc.y


def lid_vert_ids():
    return {v for p in me.polygons if p.material_index in slots(lambda n: n == LID_MAT) for v in p.vertices}


# ── 1) 색·재질을 얼굴에 맞춘다 ─────────────────────────────
face_mat = next(m for m in bpy.data.materials if m.name.startswith("tripo"))
face_bsdf = principled(face_mat)

factor, img = (1.0, 1.0, 1.0), None
bc = face_bsdf.inputs["Base Color"]
link = bc.links[0].from_node if bc.is_linked else None
if link and link.type == "MIX":
    for inp in link.inputs:
        if inp.type != "RGBA":
            continue
        if inp.is_linked and inp.links[0].from_node.type == "TEX_IMAGE":
            img = inp.links[0].from_node.image
        elif not inp.is_linked and tuple(inp.default_value)[:3] != (0.0, 0.0, 0.0):
            factor = tuple(inp.default_value)[:3]
elif link and link.type == "TEX_IMAGE":
    img = link.image
if img is None:
    raise SystemExit("얼굴 텍스처를 찾지 못했다")

W, H = img.size
px = list(img.pixels)
uvlayer = me.uv_layers.active.data
face_slots = slots(lambda n: n.startswith("tripo"))

cols = []
for p in me.polygons:
    if p.material_index not in face_slots:
        continue
    for li in p.loop_indices:
        co = me.vertices[me.loops[li].vertex_index].co
        if 30 < abs(co.x) < 40 and 30 < co.z < 50 and co.y < -25:   # 눈 바깥 볼
            u, v = uvlayer[li].uv
            x = min(W - 1, max(0, int(u * W)))
            y = min(H - 1, max(0, int(v * H)))
            i = (y * W + x) * 4
            cols.append((px[i], px[i + 1], px[i + 2]))
if not cols:
    raise SystemExit("볼 영역 샘플을 못 구했다")

tex_avg = tuple(sum(c[k] for c in cols) / len(cols) for k in range(3))
target = tuple(tex_avg[k] * factor[k] for k in range(3))
face_rough = face_bsdf.inputs["Roughness"].default_value

lid_bsdf = principled(bpy.data.materials.get(LID_MAT))
if lid_bsdf is None:
    raise SystemExit("ExLid 재질이 없다")
print(f"ExLid 색 {tuple(round(v,4) for v in lid_bsdf.inputs['Base Color'].default_value)}"
      f" -> {tuple(round(v,4) for v in target)}, "
      f"roughness {lid_bsdf.inputs['Roughness'].default_value} -> {face_rough}")
lid_bsdf.inputs["Base Color"].default_value = (*target, 1.0)
lid_bsdf.inputs["Roughness"].default_value = face_rough

# 모든 재질이 알파 1.0 인데 HASHED(스토캐스틱 알파) 로 들어와 있어, 겹친 면의 앞뒤 판정이
# 흔들리며 덮개 아래 그려진 눈이 얼룩덜룩 비쳤다. 전부 불투명으로 못박는다 —
# three.js 쪽에서도 transparent=false 가 맞다.
flipped = []
for m in bpy.data.materials:
    b = principled(m)
    if b and b.inputs["Alpha"].default_value >= 1.0 and getattr(m, "blend_method", "OPAQUE") != "OPAQUE":
        m.blend_method = "OPAQUE"
        flipped.append(m.name)
if flipped:
    print(f"blend HASHED -> OPAQUE: {', '.join(flipped)}")

# ── 2) 돔의 뒤쪽 절반을 지운다 ─────────────────────────────
bvh = face_surface_bvh()
doomed = []
for vi in lid_vert_ids():
    sy = surface_y_of(vi)
    if sy is not None and (sy - me.vertices[vi].co.y) < KEEP_BACK:
        doomed.append(vi)

if doomed:
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.verts[i] for i in doomed], context="VERTS")
    bm.to_mesh(me)
    bm.free()
    me.update()
    print(f"덮개 뒤쪽 절반 {len(doomed)} 정점 삭제")
else:
    print("지울 뒤쪽 절반 없음 — 이미 적용된 파일")

# ── 3) 남은 껍데기를 얼굴 표면에 밀착 + 법선 맞추기 ──────────
bvh = face_surface_bvh()                     # 삭제로 인덱스가 바뀌었으니 다시 만든다
face_slots = slots(lambda n: n.startswith("tripo"))
lid_slots = slots(lambda n: n == LID_MAT)
orig_normals = [tuple(cn.vector) for cn in me.corner_normals]

# 얼굴의 부드러운 정점 법선 (루프 법선을 정점별 평균)
face_vn = {}
for p in me.polygons:
    if p.material_index not in face_slots:
        continue
    for li in p.loop_indices:
        vi = me.loops[li].vertex_index
        acc = face_vn.setdefault(vi, [0.0, 0.0, 0.0])
        n = orig_normals[li]
        acc[0] += n[0]; acc[1] += n[1]; acc[2] += n[2]
face_ids = list(face_vn)
for vi in face_ids:
    v = Vector(face_vn[vi])
    face_vn[vi] = tuple(v.normalized()) if v.length > 1e-6 else (0.0, -1.0, 0.0)

kd = KDTree(len(face_ids))
for i, vi in enumerate(face_ids):
    kd.insert(me.vertices[vi].co, i)
kd.balance()

lid_ids = lid_vert_ids()
moved, missed, normal_of = 0, 0, {}
for vi in lid_ids:
    sy = surface_y_of(vi)
    if sy is None:
        missed += 1
        continue
    me.vertices[vi].co.y = sy - OFFSET
    moved += 1
    _, idx, _ = kd.find(me.vertices[vi].co)
    normal_of[vi] = face_vn[face_ids[idx]]

lid_polys = {p.index for p in me.polygons if p.material_index in lid_slots}

# flat 셰이딩이면 커스텀 법선이 무시돼 각져 보인다 — 덮개는 반드시 smooth 로.
flat = [p for p in me.polygons if p.index in lid_polys and not p.use_smooth]
for p in flat:
    p.use_smooth = True
if flat:
    print(f"덮개 폴리곤 {len(flat)} 개를 flat -> smooth 로 전환")

new_normals = list(orig_normals)
for p in me.polygons:
    if p.index not in lid_polys:
        continue
    for li in p.loop_indices:
        n = normal_of.get(me.loops[li].vertex_index)
        if n:
            new_normals[li] = n
me.normals_split_custom_set(new_normals)

print(f"남은 덮개 정점 {len(lid_ids)} 중 {moved} 개를 얼굴 표면 앞 {OFFSET} 에 밀착 (레이 빗나감 {missed})")

bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", export_animations=True)
print("EXPORTED:", dst)
