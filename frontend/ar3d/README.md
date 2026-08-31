# ar3d — 아르 3D 캐릭터 에셋 도구

에이전트 캐릭터 "아르"의 3D 모델(`../app/public/ar.glb`)을 고치는 Blender 스크립트.
프론트에서 쓰는 뷰어는 [`../app/src/components/ArViewer.tsx`](../app/src/components/ArViewer.tsx),
모션 확인용 화면은 `/dev/ar`([`ArDemo.tsx`](../app/src/pages/ArDemo.tsx)).

> 2026-08-25 파이프라인 작업의 재생성 스크립트·README(`아르-3D-작업.zip`)가 유실돼,
> 2026-08-31 enter 모션을 고치면서 필요한 만큼 여기에 다시 만들었다. **또 잃지 않게 repo 에 둔다.**

## 에셋 구조

`ar.glb` 하나에 메시·리그·모션 7종이 전부 들어 있다.

| 모션 | 프레임 | 재생 |
|---|---|---|
| `idle` | 1 | 루프(정지 포즈) |
| `enter` | 1–18 | 1회 → idle |
| `listen` | 1–32 | 루프 |
| `think` | 1–36 | 루프 |
| `ask` | 1–40 | 루프 |
| `confirm` | 1–24 | 1회 → idle |
| `fail` | 1–36 | 1회 → idle |

24fps. 본은 `Root`(전체 이동) · `Head`(스쿼시·스트레치) · `Cone` · `EarL`/`EarR` ·
`SeedSlot`/`SproutSlot`(머리 위 씨앗→새싹) · `ExAsk`/`ExHappy`/`ExSad`(표정).

**표정은 텍스처가 아니라 입체 세트 본의 스케일 교체다** — `1` = 표시, `0.001` = 숨김.
표정 세트가 그리는 건 **눈뿐이다**(좌우 `|x|` 9~28). 코는 기본 메시의 초록 돌기 하나로 고정 —
원래는 세트마다 얼굴 중앙에 자기 `ExInk` 코 마크가 있어서 표정이 바뀔 때마다 코가 링·아치로
변했고, 2026-08-31 에 [`fix_expression_nose.py`](fix_expression_nose.py) 로 그 중앙 잉크를 걷어냈다.
각 모션 애니메이션에 내장돼 있어서 `ask` → ExAsk, `confirm` → ExHappy, `fail` → ExSad,
나머지는 셋 다 숨김(기본 얼굴). 뷰어에서 표정을 강제하려면 `mixer.update()` **뒤에**
본 스케일을 덮어써야 한다(애니메이션이 매 프레임 이 채널을 쓰므로).

바탕화면에 있는 원본들(`아르_rigged.glb`, `아르_rig.blend`, `아르_anim.blend`, `아르_face.blend`)은
repo 밖이며 폴백용이다. `아르_rig.blend` 에는 액션이 없고, `아르_anim.blend` 에는 표정 리그가 없다 —
**세 요소가 다 합쳐진 건 `ar.glb` 뿐이라, 수정은 glb 를 임포트해서 하는 게 맞다.**

## 쓰는 법

Blender 5.2 (`C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`), headless.

현재 값 확인:

```bash
blender -b --python inspect_glb.py > dump.txt
```

enter 모션 재생성 (`../app/public/ar.glb` 제자리 갱신):

```bash
blender -b --python edit_enter.py
```

표정 코 마크 제거(이미 적용돼 있다. 다시 돌려도 안전):

```bash
blender -b --python fix_expression_nose.py
```

현재 enter 는 **위치만 움직인다** — 화면 밖 아래(-170)에서 감속하며 떠올라 정점(+26, f10)을 찍고,
가속하며 내려와 f16 에 착지한 뒤 정지. 스쿼시·스트레치나 씨앗 팝 같은 빠른 확대축소는 넣지 않는다
(2026-08-31 결정 — 몸이 급하게 늘었다 줄었다 하는 게 거슬린다는 피드백).

높이·타이밍을 바꾸려면 `edit_enter.py` 상단의 `rise`/`fall`/`hold` 테이블만 고치고 다시 돌린다.
같은 파일에 여러 번 돌려도 결과는 같다 — enter 곡선을 통째로 교체하기 때문.
돌린 뒤엔 `/dev/ar` 에서 눈으로 확인한다.

## 주의

- **Blender 4.4+ 는 slotted action** 이라 `action.fcurves` 가 없다.
  `action.layers[].strips[].channelbags[].fcurves` 를 쓴다(두 스크립트 모두 이 경로).
- 모션 간 크로스페이드가 튀지 않게, **애니메이션 대상이 아닌 채널도 상수 키로 남긴다**.
  채널을 지우면 그 본이 이전 모션 포즈를 그대로 물고 있게 된다.
- 어떤 채널의 애니메이션을 걷어낼 때, **상수로 굳힐 값을 소스 glb 의 f1 에서 가져오면 안 된다** —
  그 프레임이 마침 극단 포즈일 수 있다(예전 enter 는 f1 에서 Head 가 1.25 로 늘어나 있고
  씨앗이 0.001 로 숨겨져 있었다). idle 포즈 값을 확인해서 `edit_enter.py` 의 `RESTING` 에 적는다.
- 재질 색을 새로 만들 일이 있으면 sRGB → linear 변환이 필요하다.
