/// 토큰 보관 — Android Keystore 를 쓴다.
///
/// `shared_preferences` 는 평문 XML 이라 쓰지 않는다. 루팅된 폰이나 백업에서
/// 그대로 읽힌다 — 12시간짜리라도 남의 계정으로 들어갈 수 있는 값이다.
///
/// 서버는 **리프레시 토큰을 주지 않는다** (`TokenResponse` 는 access_token 하나).
/// 그래서 여기 저장하는 것도 하나뿐이고, 만료되면 갱신이 아니라 재로그인이다.
library;

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class TokenStore {
  const TokenStore([this._storage = const FlutterSecureStorage()]);

  final FlutterSecureStorage _storage;

  static const _key = 'arda.access_token';

  Future<String?> read() async {
    try {
      return await _storage.read(key: _key);
    } on Exception catch (e) {
      // 기기 암호화 키가 바뀌면(공장 초기화·백업 복원) 읽기가 실패한다.
      // 토큰이 없는 것과 같게 다뤄 로그인 화면으로 보낸다 — 앱이 죽는 것보다 낫다.
      //
      // **삼키되 보이게 한다.** 조용히 null 을 주면 저장소가 죽은 것과 그냥
      // 로그인 전인 것이 화면에서 똑같아 보인다
      if (kDebugMode) debugPrint('[auth] 토큰을 읽지 못했다: $e');
      return null;
    }
  }

  Future<void> write(String token) => _storage.write(key: _key, value: token);

  /// **최선 노력이다.** 지우기가 실패해도 던지지 않는다 — 로그아웃을 눌렀는데
  /// 화면이 안 넘어가면 사용자는 나갈 방법이 없다. 저장소가 죽은 상황이면
  /// 읽기도 실패해서([read] 가 null 을 준다) 결과적으로 로그아웃과 같아진다.
  ///
  /// 테스트 환경에도 이 경로로 들어온다 — 플랫폼 채널이 없어 delete 가
  /// MissingPluginException 을 던진다.
  Future<void> clear() async {
    try {
      await _storage.delete(key: _key);
    } on Exception {
      // 위 주석 참고
    }
  }
}
