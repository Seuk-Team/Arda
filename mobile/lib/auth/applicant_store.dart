/// 지원자 토큰 보관 (2026-09-08).
///
/// **담당자 토큰([TokenStore])과 키부터 나눠 둔다.** 한 기기에 둘 다 있을 수
/// 있고(시연에서 실제로 그 흐름이 있다), 같은 키를 쓰면 서로 덮어써 둘 중
/// 하나가 조용히 로그아웃된다. 서버도 토큰 종류(`typ`)를 갈라 보므로 섞이면
/// 그냥 401 이 나는데, 화면에는 "다시 로그인해 주세요" 로만 보여 원인을 찾기
/// 어렵다 (ADR-0031).
///
/// ## 링크 목록에서 토큰 하나로
///
/// 예전에는 메일 링크의 토큰을 종류별로 모아 뒀다. 서버에 지원자 로그인이
/// 생기면서(ADR-0031) **JWT 하나**로 바뀌었다 — 그 토큰으로 `GET /applicant/me`
/// 를 부르면 지원·면접·인적성·일정 토큰이 한 번에 온다.
///
/// ## 얼마나 사나
///
/// **2시간**이고 리프레시가 없다 — 만료되면 갱신이 아니라 재로그인이다.
/// 비밀번호가 생년월일이라 새어도 바꿀 방법이 없어 짧게 잡은 것이다.
/// `GET /applicant/me` 가 401 을 주면 만료이고, 그때 [clear] 하고 로그인
/// 화면으로 보낸다.
///
/// **면접 중 만료는 걱정하지 않아도 된다** — 면접은 지원자 토큰이 아니라
/// 면접 토큰으로 돈다. 로그인이 풀려도 면접 화면은 그대로 굴러간다.
library;

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../api/api_client.dart';

class ApplicantStore {
  const ApplicantStore([this._storage = const FlutterSecureStorage()]);

  final FlutterSecureStorage _storage;

  /// 담당자는 `arda.access_token` 이다. 웹도 `arda-token` /
  /// `arda-applicant-token` 으로 같이 나눠 뒀다
  static const _key = 'arda.applicant_token';

  Future<String?> read() async {
    try {
      return await _storage.read(key: _key);
    } on Exception catch (e) {
      // 기기 암호화 키가 바뀌면(공장 초기화·백업 복원) 읽기가 실패한다.
      // 토큰이 없는 것과 같게 다뤄 로그인 화면으로 보낸다 — 앱이 죽는 것보다 낫다.
      //
      // **삼키되 보이게 한다** ([TokenStore] 와 같은 판단)
      if (kDebugMode) debugPrint('[applicant] 토큰을 읽지 못했다: $e');
      return null;
    }
  }

  Future<void> write(String token) async {
    try {
      await _storage.write(key: _key, value: token);
    } on Exception catch (e) {
      // 저장에 실패해도 이번 세션은 굴러간다(메모리에는 있다).
      // 다음에 앱을 켜면 다시 로그인해야 할 뿐이다
      if (kDebugMode) debugPrint('[applicant] 토큰을 저장하지 못했다: $e');
    }
  }

  /// 지원자로서 나가기. **최선 노력이다** — 실패해도 던지지 않는다
  /// ([TokenStore.clear] 와 같은 이유: 나갈 방법이 없으면 안 된다)
  Future<void> clear() async {
    try {
      await _storage.delete(key: _key);
    } on Exception {
      // 위 주석 참고
    }
  }
}

/// 토큰이 붙은 [ApiClient] 를 만든다 — 지원자 저장소는 이걸 쓴다.
///
/// 담당자 쪽 `authedClient()` 와 같은 모양이다. **다른 것은 어느 토큰을
/// 붙이냐뿐**이고, 401 이면 그 토큰을 버리는 것도 같다.
ApiClient applicantClient([ApplicantStore store = const ApplicantStore()]) =>
    ApiClient(readToken: store.read, onAuthExpired: store.clear);
