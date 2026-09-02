/// API 서버 주소 — **빌드할 때 넣는다** (2026-09-02 결정).
///
/// 앱은 웹과 달리 서버 주소를 스스로 알 수 없다. 웹은 arda.seuk.cloud 에서
/// 열리니 같은 도메인으로 물어보면 되지만, 앱은 폰에 설치돼 있어 절대 주소가
/// 필요하다.
///
///     flutter build apk                                                 # 배포 서버
///     flutter build apk --dart-define=API_BASE=http://192.168.0.5:8000  # 내 PC
///
/// **코드에 박지 않는 이유**: 로컬 주소로 고쳐 두고 되돌리기를 깜빡하면 내
/// 노트북 주소로 붙는 APK 를 팀에 배포하게 된다. 받는 사람에게는 그냥 앱이
/// 안 되는 것으로만 보여서 원인을 못 찾는다. 기본값을 배포 주소로 두면
/// 평소에는 `flutter build apk` 만 쓰면 되고 되돌릴 것이 없다.
///
/// **설정 화면에 입력칸을 두지 않는 이유**: 서버 주소가 설치처마다 다른
/// 제품(사내 설치형)에서 쓰는 방식이다. 우리는 서버가 하나뿐이고, 발표용 앱
/// 설정에 개발자용 칸이 남는다.
///
/// **로컬 백엔드에 붙일 때 `localhost` 는 안 된다** — 폰 입장에서 localhost 는
/// 폰 자신이다. PC 의 LAN 주소(`ipconfig` 의 IPv4)를 써야 한다.
library;

abstract final class ApiConfig {
  /// 서버 주소. `--dart-define=API_BASE=...` 로 덮어쓴다
  static const host = String.fromEnvironment(
    'API_BASE',
    defaultValue: 'https://api.arda.seuk.cloud',
  );

  /// **경로 접두어.** 02-api.md 표에는 `/auth/login` 처럼 적혀 있지만 실제 서버는
  /// `/api/v1/auth/login` 이다 — 문서가 접두어를 생략했다(2026-09-02 실측:
  /// `GET https://api.arda.seuk.cloud/openapi.json`).
  ///
  /// 여기 한 곳에만 두고 각 호출은 짧은 경로를 쓴다. 큐 8 에서 엔드포인트가
  /// 50개 넘게 붙는데 저마다 접두어를 적으면 한 번 바뀔 때 전부 고쳐야 한다.
  static const prefix = '/api/v1';

  /// 요청이 실제로 붙는 곳
  static const base = '$host$prefix';

  /// 서버가 죽었을 때 무한정 기다리지 않는다. 05-design §6 의 오류 상태로
  /// 떨어뜨리는 편이 "멈춘 화면" 보다 낫다
  static const timeout = Duration(seconds: 15);
}
