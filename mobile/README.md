# Arda 모바일 앱

담당자·면접관용 **Android 앱**. 웹과 같은 API를 쓰는 두 번째 클라이언트다.

- 오너: minahdev · 로드맵: [docs/01_role/app.md](../docs/01_role/app.md)
- 스택 결정 근거: [ADR-0010](../docs/03_decision/0010-앱-flutter-확정.md)
- 디자인 규칙: [docs/00_overview/05-design.md](../docs/00_overview/05-design.md)

## 확정된 값

| | | |
|---|---|---|
| 앱 ID | `cloud.seuk.arda` | **확정** (2026-08-26, 팀장 확인) — 팀 도메인 `seuk.cloud`를 거꾸로 쓴 값 |
| 대상 OS | **Android 전용** | iOS는 코드 호환만 유지하고 빌드·시연하지 않는다 (ADR-0010) |
| 폰트 | IBM Plex Sans KR (400·600) | `assets/fonts/`에 번들. SIL OFL 1.1 |

앱 ID는 Play 스토어에 올리면 영영 못 바꾼다. `android/app/build.gradle.kts`의
`applicationId`와 `ios/Runner.xcodeproj`의 `PRODUCT_BUNDLE_IDENTIFIER`가 같은 값이어야 한다.

## 실행

```bash
flutter devices          # 폰이 잡히는지 확인
flutter run              # 디버그 실행
```

기기는 **Android 실기기 또는 에뮬레이터**여야 한다. Windows·Chrome 대상은 만들지 않았다.

## 검증

```bash
flutter analyze          # 경고 0 유지
flutter test
```

`flutter analyze` 무경고는 **iOS 호환을 확인할 수 있는 유일한 수단**이다 (Mac이 없어 iOS 빌드를 못 돌린다 — ADR-0010).

## 구조

```
lib/
  main.dart          앱 진입점 · 라우트 등록 · 폰트 라이선스 등록
  routes.dart        화면 경로 이름
  theme/
    tokens.dart      05-design 확정값 (웹 tokens.css 에서 이식)
    app_theme.dart   토큰 → ThemeData
  screens/           화면별 위젯
assets/fonts/        IBM Plex Sans KR + OFL.txt
```

**색·크기·간격을 화면 코드에 직접 쓰지 않는다.** 토큰에 없는 값이 필요하면
05-design에 토큰으로 추가한 뒤(팀장 승인) `tokens.dart`에 옮긴다.
