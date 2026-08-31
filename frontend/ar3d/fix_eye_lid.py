# 감은 눈(confirm·fail) 에서 눈 둘레에 어색한 원이 보이던 문제를 고친다.
#
# 감은 눈은 얼굴에 ExLid 덮개를 씌워 텍스처에 그려진 눈을 가리는 방식이다.
# 그 덮개가 원반처럼 도드라져 보인 건 세 가지가 겹쳐서였다:
#   (1) 색 — 얼굴은 [텍스처 × 0.8] 이라 실제 (0.456,0.543,0.277) 인데 덮개는 (0.284,0.417,0.098) 로 훨씬 어두웠다
#   (2) 재질 반응 — 얼굴 roughness 0.5 vs 덮개 1.0 이라 같은 빛을 다르게 받았다
#   (3) 형태 — 덮개가 얼굴보다 2.7 앞으로 볼록 튀어나와 빛을 더 정면으로 받았다. (1)(2)만 고쳐도 원이 남는다
# 셋 다 맞춘다. 특히 (3) 은 덮개를 얼굴 곡면에 레이캐스트로 투영해 밀착시키고,
# 법선까지 얼굴 표면 법선으로 덮어써서 음영이 얼굴과 똑같이 나오게 한다.
#
# 덮개를 통째로 뒤로 밀면 안 된다 — 곡률이 얼굴과 달라 가장자리가 얼굴 속으로 잠기고,
# 텍스처에 그려진 원래 눈이 새어 나온다(실험으로 확인). x·z 범위는 그대로 두고 y 만 표면에 붙인다.
#
#   blender -b --python fix_eye_lid.py -- [<in.glb>] [<out.glb>]
#
# 인자를 생략하면 app/public/ar.glb 를 제자리에서 갱신한다.
# 위치를 "얼굴 표면 앞 OFFSET" 이라는 절대값으로 잡으므로 여러 번 돌려도 결과가 같다.
import bpy, os, sys
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

OFFSET = 0.2      # 덮개 표면이 얼굴보다 최소한 이만큼은 앞에 있게 (z-fighting 방지)
FLATTEN = 0.25    # 돔 깊이를 이 비율로 눌러 납작하게. 0 으로 하면 돔이 자기 자신과 겹쳐 접혀서
                  # 검은 얼룩이 생긴다 — 구조는 유지한 채 볼록함만 줄이는 게 핵심이다.

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_GLB = os.path.join(HERE, "..", "app", "public", "ar.glb")

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
src = os.path.abspath(argv[0]) if len(argv) > 0 else os.path.abspath(DEFAULT_GLB)
dst = os.path.abspath(argv[1]) if len(argv) > 1 else src

LID_MAT = "ExLid"

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)


def principled(mat):
    if not (mat and mat.use_nodes):
        return None
    return next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)


# --- 얼굴이 실제로 내는 색 = 텍스처 평균 × baseColorFactor ---
face_mat = next(m for m in bpy.data.materials if m.name.startswith("tripo"))
face_bsdf = principled(face_mat)

# Base Color 에 물린 Mix 노드에서 텍스처와 factor 를 꺼낸다
factor = (1.0, 1.0, 1.0)
img = None
link = face_bsdf.inputs["Base Color"].links[0].from_node if face_bsdf.inputs["Base Color"].is_linked else None
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

# 눈 옆 볼 부분의 텍스처 색을 샘플링 (얼굴 초록. 그려진 눈·입은 피한다)
obj = next(o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("Aru"))
me = obj.data
W, H = img.size
px = list(img.pixels)
uvlayer = me.uv_layers.active.data
face_slots = {i for i, m in enumerate(me.materials) if m and m.name.startswith("tripo")}

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
n = len(cols)
tex_avg = tuple(sum(c[k] for c in cols) / n for k in range(3))
target = tuple(tex_avg[k] * factor[k] for k in range(3))
face_rough = face_bsdf.inputs["Roughness"].default_value

print(f"얼굴 텍스처 평균 {tuple(round(v,4) for v in tex_avg)} × factor {tuple(round(v,3) for v in factor)}"
      f" = {tuple(round(v,4) for v in target)} / roughness {face_rough}")

lid_bsdf = principled(bpy.data.materials.get(LID_MAT))
if lid_bsdf is None:
    raise SystemExit("ExLid 재질이 없다")
before_c = tuple(round(v, 4) for v in lid_bsdf.inputs["Base Color"].default_value)
before_r = lid_bsdf.inputs["Roughness"].default_value
lid_bsdf.inputs["Base Color"].default_value = (*target, 1.0)
lid_bsdf.inputs["Roughness"].default_value = face_rough
print(f"ExLid 색 {before_c} -> {tuple(round(v,4) for v in target)} , roughness {before_r} -> {face_rough}")

# --- 덮개를 얼굴 곡면에 밀착 ---
lid_slots = {i for i, m in enumerate(me.materials) if m and m.name == LID_MAT}
lid_polys = [p for p in me.polygons if p.material_index in lid_slots]
lid_verts = {v for p in lid_polys for v in p.vertices}

# 얼굴 폴리곤만으로 BVH 를 만든다 (덮개 자신에 레이가 맞지 않게)
bvh = BVHTree.FromPolygons(
    [tuple(v.co) for v in me.vertices],
    [list(p.vertices) for p in me.polygons if p.material_index in face_slots],
    all_triangles=False,
)

# 정점을 옮기기 전에 원래 법선을 읽어 둔다 (커스텀 법선 CORNER 도메인)
orig_normals = [tuple(cn.vector) for cn in me.corner_normals]

# 얼굴의 부드러운 정점 법선 (루프 법선을 정점별로 평균).
# 레이캐스트가 주는 면 법선을 쓰면 각지고 일부는 뒤를 향해 검게 나온다 — 반드시 이 쪽을 쓴다.
face_vert_normals = {}
for p in me.polygons:
    if p.material_index not in face_slots:
        continue
    for li in p.loop_indices:
        vi = me.loops[li].vertex_index
        acc = face_vert_normals.setdefault(vi, [0.0, 0.0, 0.0])
        n = orig_normals[li]
        acc[0] += n[0]; acc[1] += n[1]; acc[2] += n[2]
face_ids = list(face_vert_normals)
for vi in face_ids:
    v = Vector(face_vert_normals[vi])
    face_vert_normals[vi] = tuple(v.normalized()) if v.length > 1e-6 else (0.0, -1.0, 0.0)

kd = KDTree(len(face_ids))
for i, vi in enumerate(face_ids):
    kd.insert(me.vertices[vi].co, i)
kd.balance()

# 얼굴 표면 대비 각 정점이 튀어나온 정도
surface_y, missed = {}, 0
for vi in lid_verts:
    co = me.vertices[vi].co
    # 얼굴 한참 앞에서 뒤(+y)로 쏴서 앞면을 맞힌다
    loc, _, _, _ = bvh.ray_cast(Vector((co.x, -500.0, co.z)), Vector((0.0, 1.0, 0.0)))
    if loc is None:
        missed += 1
        continue
    surface_y[vi] = loc.y

max_gap = max((surface_y[vi] - me.vertices[vi].co.y for vi in surface_y), default=0.0)
already = max_gap < 1.5      # 원본 돌출은 2.74, 적용 후는 ~0.9 → 재실행 시 또 누르지 않게

hit_normal = {}
for vi in surface_y:
    if not already:
        gap = surface_y[vi] - me.vertices[vi].co.y
        me.vertices[vi].co.y = surface_y[vi] - OFFSET - gap * FLATTEN
    _, idx, _ = kd.find(me.vertices[vi].co)      # 가장 가까운 얼굴 정점의 부드러운 법선
    hit_normal[vi] = face_vert_normals[face_ids[idx]]

print(f"ExLid 정점 {len(lid_verts)}, 최대 돌출 {max_gap:.2f}"
      + (" — 이미 적용됨, 형태 유지" if already
         else f" -> {OFFSET + max_gap * FLATTEN:.2f} 로 납작하게")
      + f" (레이 빗나감 {missed})")

# 덮개 루프의 법선을 얼굴 표면 법선으로 교체 → 음영이 얼굴과 같아진다
lid_poly_ids = {p.index for p in lid_polys}
new_normals = list(orig_normals)
for p in me.polygons:
    if p.index not in lid_poly_ids:
        continue
    for li in p.loop_indices:
        n = hit_normal.get(me.loops[li].vertex_index)
        if n:
            new_normals[li] = n
me.normals_split_custom_set(new_normals)

bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", export_animations=True)
print("EXPORTED:", dst)
