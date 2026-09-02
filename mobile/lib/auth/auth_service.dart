/// 로그인·자동 로그인·로그아웃 — 인증에 관한 일을 한 자리에 모은다.
///
/// 화면은 이 클래스만 부른다. 토큰을 어디에 어떻게 넣는지, 401 이면 무엇을
/// 지우는지는 화면이 알 필요가 없다.
///
/// **02-api.md**
/// - `POST /auth/login` `{email, password}` → `{access_token, token_type}`
/// - `GET /auth/me` → `UserOut`
/// - `PATCH /auth/me` `{name?, current_password?, new_password?}`
library;

import '../api/api_client.dart';
import '../api/api_error.dart';
import '../models/app_user.dart';
import 'token_store.dart';

class AuthService {
  AuthService({ApiClient? client, TokenStore store = const TokenStore()})
    : _store = store {
    _client =
        client ??
        ApiClient(
          readToken: store.read,
          // 401 을 받으면 죽은 토큰을 들고 있을 이유가 없다
          onAuthExpired: store.clear,
        );
  }

  late final ApiClient _client;
  final TokenStore _store;

  ApiClient get client => _client;

  /// 로그인. 성공하면 토큰을 저장하고 내 정보를 돌려준다.
  ///
  /// 비밀번호가 틀리면 [LoginFailed], 서버에 못 닿으면 [NetworkError] 다 —
  /// 화면이 다른 문구를 띄워야 해서 나뉜다.
  Future<AppUser> login({
    required String email,
    required String password,
  }) async {
    final res = await _client.post(
      '/auth/login',
      body: {'email': email, 'password': password},
      // 아직 토큰이 없다. 이 플래그가 401 을 "만료" 가 아니라 "틀렸다" 로 만든다
      authenticated: false,
    );

    final token = res['access_token'] as String?;
    if (token == null || token.isEmpty) {
      throw const ServerError(200, '토큰을 받지 못했습니다.');
    }
    await _store.write(token);

    return me();
  }

  /// 지금 토큰으로 내가 누구인지 묻는다.
  Future<AppUser> me() async =>
      AppUserJson.fromJson(await _client.get('/auth/me'));

  /// 앱을 켤 때 부른다 — 저장된 토큰이 아직 쓸 수 있으면 그 사용자를 준다.
  ///
  /// 토큰이 없거나(첫 실행·로그아웃 뒤) 만료됐으면 null 이다. **네트워크가
  /// 끊긴 것은 다르다** — 토큰이 죽은 것이 아니므로 [NetworkError] 를 그대로
  /// 올려보내 화면이 "다시 시도" 를 줄 수 있게 한다. 여기서 null 로 뭉개면
  /// 지하철에서 앱을 켰다고 로그아웃되는 셈이다.
  Future<AppUser?> restore() async {
    if (await _store.read() == null) return null;
    try {
      return await me();
    } on AuthExpired {
      return null;
    }
  }

  /// 이름·비밀번호 변경 (G4). `current_password` 없이 비밀번호를 바꾸려 하면
  /// 서버가 422 로 막는다 — 화면에서도 막지만 최종 판정은 서버다.
  Future<AppUser> updateMe({
    String? name,
    String? currentPassword,
    String? newPassword,
  }) async {
    final res = await _client.patch(
      '/auth/me',
      body: {
        'name': ?name,
        'current_password': ?currentPassword,
        'new_password': ?newPassword,
      },
    );
    return AppUserJson.fromJson(res);
  }

  /// 토큰을 지운다. 서버에 알릴 것은 없다 — 상태를 갖지 않는 JWT 라
  /// 로그아웃 엔드포인트가 없고, 남은 12시간은 그냥 만료를 기다린다.
  Future<void> logout() => _store.clear();
}
