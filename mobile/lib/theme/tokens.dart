/// 디자인 토큰 — docs/00_overview/05-design.md 확정값을 Dart 로 이식한 것.
///
/// 원본은 웹의 `frontend/app/src/tokens.css` 다. **값을 여기서 새로 만들지 않는다.**
/// 토큰에 없는 값이 필요해지면 05-design 에 토큰으로 추가한 뒤(프론트 오너 판단) 여기에 옮긴다.
///
/// CSS 변수명을 그대로 살려 뒀다 — `--bg-sunken` ↔ `AppColors.bgSunken` 처럼
/// 웹과 나란히 놓고 대조할 수 있어야 하기 때문이다.
library;

import 'package:flutter/widgets.dart';

/// 색 — 05-design §1. 색마다 이유가 문서에 있다. 임의 색 추가 금지.
///
/// **2026-09-07 다크 이식.** 웹이 라이트 새싹 팔레트를 딥 네트워크 다크로
/// 뒤집은 것을 그대로 옮겼다(`frontend/app/src/tokens.css`). 두 클라이언트가
/// 다른 색이면 같은 제품으로 안 보인다.
///
/// 가장 큰 변화는 색이 아니라 **재질**이다. 면이 불투명한 흰 판이 아니라
/// 유리다 — 알파가 있어야 뒤의 바탕이 비친다.
abstract final class AppColors {
  /// 바탕. 이 위에 오로라가 깔린다
  static const bg = Color(0xFF070B14);

  /// 카드·패널의 얼굴 — 유리. 알파가 있어야 뒤가 비친다 (rgba(13,19,34,.62))
  static const bgElev = Color(0x9E0D1322);

  /// 셸 크롬(상단 바·하단 탭): 본문 카드보다 한 겹 더 가라앉는다 (rgba(9,13,24,.66))
  static const bgChrome = Color(0xA8090D18);

  /// 인풋·트랙·줄무늬. 라이트에선 아래로 팠지만 다크에선 **위로 올린다** —
  /// 어두운 바탕을 더 어둡게 하면 그냥 구멍이 된다 (rgba(255,255,255,.055))
  static const bgSunken = Color(0x0EFFFFFF);

  /// sunken 바탕 위 hover 채움 (rgba(255,255,255,.10))
  static const sunkenHover = Color(0x1AFFFFFF);

  static const sidebarBg = bgChrome;
  static const sidebarLine = Color(0x17FFFFFF);

  /// 유리 윗면에 닿는 빛. 다크에서 면을 띄우는 것은 그림자가 아니라 이 한 줄이다
  static const glassInset = Color(0x0FFFFFFF);

  static const text = Color(0xFFF2F5FB);
  static const textSub = Color(0xFF9AA7C0);

  static const border = Color(0x1FFFFFFF);
  static const borderSoft = Color(0x12FFFFFF);

  /// ── 강조: 시안 → 블루 → 바이올렛 ──────────────────────
  /// 배경 노드망이 쓰는 팔레트를 그대로 UI 로 가져온다
  static const accent = Color(0xFF22D3EE);
  static const accentBlue = Color(0xFF60A5FA);
  static const accentViolet = Color(0xFFA78BFA);

  /// 어두운 바탕에서 #22D3EE 는 글자로 쓰기엔 탁하다 — 글자·테두리는 한 톤 밝게
  static const accentText = Color(0xFF7DD3FC);

  /// 주 동작 채움. **네온이 아니라 흰 판이다** — 네온이 이미 배경에 깔려 있어
  /// 버튼까지 빛나면 무엇이 동작인지 안 읽힌다
  static const accentFill = Color(0xFFFFFFFF);
  static const onAccent = Color(0xFF0A1020);

  /// 시안 워시 — 활성 메뉴 판·hover 채움 (rgba(34,211,238,.13))
  static const accentSoft = Color(0x2122D3EE);

  /// 판단 전(접수·서류·면접) 공용 — "색 없음"이 의미
  static const neutral = Color(0xFF7D8CA8);

  /// 불합격·실패. 다크에서 벽돌색(#A9503C)은 바탕에 먹혀 안 읽힌다 — 살구로 올렸다
  static const danger = Color(0xFFF0A38F);
  static const dangerSoft = Color(0x21F0A38F);

  /// 합격·성공
  static const ok = Color(0xFF34D399);
  static const okSoft = Color(0x2134D399);
  static const okText = Color(0xFF6EE7B7);

  /// 주의·만료 임박
  static const warn = Color(0xFFFBBF24);
  static const warnText = Color(0xFFFCD34D);

  /// AI 생성물 — 앰버 **점선** 규약 (실선은 사람 확정)
  static const ai = Color(0xFFFCD34D);
  static const aiSoft = Color(0x33A9702A);
  static const aiLine = Color(0xFFA9702A);

  /// 퍼널 레일 진행 구간 전용 램프 — 흐름 그래프 한정 허용 (05-design §1).
  /// 2026-09-07 웹에서 밝기 간격을 벌렸다(인접 ΔE 9.6 → 15.9): 셋이 다
  /// 회색으로 보여 구분이 안 됐다. 색상·채도는 그대로 — 무채 규칙이 있어
  /// 손댈 수 있는 건 밝기뿐이었다.
  static const stage1 = Color(0xFF3A4762);
  static const stage2 = Color(0xFF667592);
  static const stage3 = Color(0xFF95A5C4);
  static const stage4 = ok;

  static const funnelRamp = <Color>[stage1, stage2, stage3];

  /// ── 옛 이름 (라이트 팔레트 잔재) ────────────────────────
  /// 이름은 더 이상 색을 설명하지 않는다. 화면 코드가 80곳 가까이 쓰고 있어
  /// 한 번에 못 걷었다 — 새 코드에서는 쓰지 말고, 고칠 때마다 위 이름으로 옮긴다.
  @Deprecated('accent 를 쓴다 — 면·채움·레일')
  static const sprout = accent;
  @Deprecated('accentSoft 를 쓴다 — 워시 배경')
  static const sproutSoft = accentSoft;
  @Deprecated('accentText 를 쓴다 — 글자·링크·강조')
  static const leaf = accentText;
  @Deprecated('accent 를 쓴다')
  static const leafStrong = accent;
}

/// 타이포 — 05-design §2. **스케일 7단계 외 크기 금지.**
abstract final class AppType {
  /// IBM Plex Sans KR 단일. 별도 mono 폰트 금지.
  ///
  /// `assets/fonts/` 에 번들돼 있다 (pubspec.yaml `fonts:`). 굵기는 400·600 2종뿐이라
  /// 그 사이 값을 쓰면 Flutter 가 가까운 쪽으로 붙인다 — 05-design 에 없는 굵기는 쓰지 않는다.
  static const fontFamily = 'IBM Plex Sans KR';

  /// 본문 굵기
  static const wRegular = FontWeight.w400;

  /// 메뉴·강조 굵기 (05-design §2: 메뉴 w600)
  static const wSemiBold = FontWeight.w600;

  /// 화면 제목
  static const display = 26.0;

  /// 섹션 제목 · 로고
  static const h1 = 22.0;

  /// 카드·패널 제목
  static const h2 = 18.0;

  /// 본문 · 메뉴
  static const body = 16.0;

  /// 보조
  static const sm = 14.0;

  /// 뱃지·메타
  static const caption = 12.0;

  /// 수치·날짜 — tabular figures 를 함께 쓴다 ([tabularNums])
  static const num = 14.0;

  /// 수치·날짜의 자리 폭 고정 (CSS `font-variant-numeric: tabular-nums`)
  static const tabularNums = <FontFeature>[FontFeature.tabularFigures()];

  /// 메뉴 항목 높이 (Material 내비 항목 48dp)
  static const menuItemHeight = 48.0;
}

/// 간격 — 05-design §3. 4px 배수 토큰만 쓴다.
abstract final class AppSpace {
  static const s1 = 4.0;
  static const s2 = 8.0;
  static const s3 = 12.0;
  static const s4 = 16.0;
  static const s5 = 24.0;
  static const s6 = 32.0;
  static const s7 = 40.0;
  static const s8 = 48.0;
}

/// 테두리·radius — 05-design §4.
abstract final class AppShape {
  static const borderW = 1.0;

  static const rCtl = Radius.circular(6);
  static const rCard = Radius.circular(8);
  static const rPill = Radius.circular(999);

  static const ctl = BorderRadius.all(rCtl);
  static const card = BorderRadius.all(rCard);
  static const pill = BorderRadius.all(rPill);
}

/// 그림자 — 05-design §4. 박스 그림자는 이 2종만. 남발 금지.
abstract final class AppShadow {
  /// 옅은 카드
  static const card = <BoxShadow>[
    BoxShadow(color: Color(0x0F1B2117), offset: Offset(0, 1), blurRadius: 2),
    BoxShadow(color: Color(0x0A1B2117), offset: Offset(0, 1), blurRadius: 1),
  ];

  /// hover·오버레이
  static const overlay = <BoxShadow>[
    BoxShadow(color: Color(0x241B2117), offset: Offset(0, 8), blurRadius: 28),
    BoxShadow(color: Color(0x0F1B2117), offset: Offset(0, 2), blurRadius: 6),
  ];
}

/// 텍스트 그림자 — 05-design §2. 글자에 딱 붙는 **블러 0 하드 오프셋**.
/// 본문·캡션 등 작은 글씨엔 그림자 금지.
abstract final class AppTextShadow {
  /// display·h1·h2 와 밝은 배경 위 어두운 버튼 글자에 **항상**
  static const heading = <Shadow>[
    Shadow(color: Color(0x571B2117), offset: Offset(0, 1)),
  ];

  /// 다크에서는 **없다**(웹 `--ts-onfill: none`). 주 동작 채움이 흰 판 +
  /// 어두운 글자라, 라이트 때 쓰던 검은 그림자를 그대로 두면 글자가 뭉갠다.
  static const onFill = <Shadow>[];
}

/// 모션 — 05-design §5. HIG·Material 권장 범위 내.
abstract final class AppMotion {
  static const fast = Duration(milliseconds: 120);
  static const base = Duration(milliseconds: 200);
  static const slow = Duration(milliseconds: 320);

  /// CSS `cubic-bezier(.2, 0, 0, 1)`
  static const ease = Cubic(0.2, 0, 0, 1);
}

/// 레이아웃 — 05-design §3·§9.
///
/// 사이드바 폭·본문 좌우 여백은 웹 전용 값이라 옮기지 않았다.
/// 앱은 768px 미만 구간만 그린다 (칸반 없음, 단계 탭 + 리스트).
abstract final class AppLayout {
  /// 터치 타깃 최소 44×44 (HIG · 05-design §9)
  static const minTouchTarget = 44.0;
}
