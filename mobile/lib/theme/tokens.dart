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
abstract final class AppColors {
  /// 녹기 한 방울 섞인 흰색 — 순백 패널이 떠 보이게 하는 받침
  static const bg = Color(0xFFF4F7F0);

  /// 주 컬러 흰색 — 카드·패널의 얼굴
  static const bgElev = Color(0xFFFFFFFF);

  /// 인풋·트랙: 패널보다 한 단계 아래
  static const bgSunken = Color(0xFFEBF0E5);

  /// sunken 바탕 위 hover 채움. 같은 자리의 press 는 [bgElev] 로 올라온다
  static const sunkenHover = Color(0xFFDCE3D4);

  static const sidebarBg = Color(0xFFC7E49B);
  static const sidebarLine = Color(0xFFA8CD6E);

  /// 순검정 대신 잎 그림자 톤 잉크
  static const text = Color(0xFF1B2117);

  /// 보조 텍스트 (위계용 최소 1단계)
  static const textSub = Color(0xFF5C6654);

  static const border = Color(0xFFDCE3D4);
  static const borderSoft = Color(0xFFEAEFE4);

  /// 새싹 연두 — 면·채움·레일·합격 전용
  static const sprout = Color(0xFF8CC63F);

  /// 연두 워시 — 합격 뱃지 배경·hover
  static const sproutSoft = Color(0xFFEFF7E2);

  /// 연두는 글자 대비 미달 → 버튼·링크·강조 글자용 짙은 잎
  static const leaf = Color(0xFF3A6B21);
  static const leafStrong = Color(0xFF2C5218);

  /// 판단 전(접수·서류·면접) 공용 — "색 없음"이 의미
  static const neutral = Color(0xFF8A9284);

  /// 불합격·실패 — 연두의 보색 계열, 종료 신호
  static const danger = Color(0xFFA9503C);
  static const dangerSoft = Color(0xFFF7ECE8);

  /// AI 제안 — 앰버 **점선** 규약 (실선은 사람 확정)
  static const ai = Color(0xFFA9702A);
  static const aiSoft = Color(0xFFFBF2E5);

  /// 퍼널 레일 진행 구간 전용 무채 램프 — 흐름 그래프 한정 허용 (05-design §1)
  static const funnelRamp = <Color>[
    Color(0xFFC9CFC3),
    Color(0xFFAEB6A8),
    neutral,
  ];
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

  /// 색 채움 배경 위 밝은 글자(버튼·토스트)에 크기 무관 **거의 항상**
  static const onFill = <Shadow>[
    Shadow(color: Color(0x9E000000), offset: Offset(0, 1)),
  ];
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
