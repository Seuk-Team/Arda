# 아르 enter 모션 재제작 — 화면 밖 아래에서 붕 떠올라 정점을 찍고 내려와 착지.
#
# glb 를 임포트해 enter 액션의 키프레임만 갈아끼우고 다시 내보낸다.
# 같은 glb 에 여러 번 돌려도 결과는 같다(enter 곡선을 통째로 교체하므로).
#
#   blender -b --python edit_enter.py -- [<in.glb>] [<out.glb>]
#
# 인자를 생략하면 app/public/ar.glb 를 제자리에서 갱신한다.
# 값(탄도 높이·되튐·타이밍)을 바꾸려면 아래 키프레임 테이블만 고치면 된다.
import bpy, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_GLB = os.path.join(HERE, "..", "app", "public", "ar.glb")

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
src = os.path.abspath(argv[0]) if len(argv) > 0 else os.path.abspath(DEFAULT_GLB)
dst = os.path.abspath(argv[1]) if len(argv) > 1 else src

# --- 키프레임 테이블 (24fps, f1~f18 = 0.75초) ---
# 움직이는 건 위치뿐이다. 스쿼시·스트레치나 씨앗 팝 같은 빠른 확대축소는 넣지 않는다.
#
# Root.location[1] = 본 로컬 y축, 월드 +Z(위). -170 은 화면 밖 아래.
# 상승은 감속(ease-out), 정점 f10 에서 잠깐 머물고, 낙하는 가속(중력).
rise = [(1, -170.0), (2, -128.9), (3, -92.6), (4, -61.1), (5, -34.6),
        (6, -12.8), (7, 4.2), (8, 16.4), (9, 23.6), (10, 26.0)]
fall = [(11, 25.3), (12, 23.1), (13, 19.5), (14, 14.4), (15, 7.9), (16, 0.0)]
hold = [(18, 0.0)]
root_y = rise + fall + hold

FIRST, LAST = 1, 18

ANIMATED = {
    ('pose.bones["Root"].location', 1): root_y,
}

# 애니메이션을 걷어낸 채널이 어떤 값으로 굳어야 하는지.
# 소스 glb 의 f1 값을 그대로 쓰면 안 된다 — 이전 버전 enter 는 f1 에서 몸이 늘어나 있고
# (Head 1.25) 씨앗이 숨겨져 있어서(0.001), 그대로 굳히면 늘어난 채 서 있거나 씨앗이 사라진다.
# idle 포즈와 같은 값으로 맞춘다.
RESTING = {
    ('pose.bones["Head"].scale', 0): 1.0,
    ('pose.bones["Head"].scale', 1): 1.0,
    ('pose.bones["Head"].scale', 2): 1.0,
    ('pose.bones["SeedSlot"].scale', 0): 1.0,
    ('pose.bones["SeedSlot"].scale', 1): 1.0,
    ('pose.bones["SeedSlot"].scale', 2): 1.0,
}

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)

act = bpy.data.actions["enter"]


def channelbag(a):
    """Blender 4.4+ slotted action: fcurve 는 layers→strips→channelbags 아래에 있다."""
    for layer in a.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                return bag
    raise RuntimeError("channelbag 없음 — Blender 4.4 미만이면 a.fcurves 를 쓴다")


bag = channelbag(act)


def set_curve(path, index, keys):
    fc = bag.fcurves.find(path, index=index)
    if fc:
        bag.fcurves.remove(fc)
    fc = bag.fcurves.new(path, index=index)
    for f, v in keys:
        kp = fc.keyframe_points.insert(f, v)
        kp.interpolation = "LINEAR"   # 완급은 위 테이블에 이미 담겨 있다
    fc.update()


# 원본과 같은 채널 커버리지를 유지한다 — 모션 간 크로스페이드가 튀지 않게,
# 애니메이션 대상이 아닌 채널도 상수 2키로 남긴다(RESTING 에 없으면 소스의 f1 값).
existing = [(fc.data_path, fc.array_index, fc.keyframe_points[0].co[1]) for fc in bag.fcurves]
for path, idx, v0 in existing:
    if (path, idx) not in ANIMATED:
        set_curve(path, idx, [(FIRST, RESTING.get((path, idx), v0)), (LAST, RESTING.get((path, idx), v0))])
for (path, idx), keys in ANIMATED.items():
    set_curve(path, idx, keys)

print("enter rebuilt: range", list(act.frame_range), "curves", len(list(bag.fcurves)))

bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", export_animations=True)
print("EXPORTED:", dst)
