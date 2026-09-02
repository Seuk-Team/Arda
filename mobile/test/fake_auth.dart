// 테스트용 가짜 인증 — 네트워크도 Keystore 도 타지 않는다.
//
// 큐 7 로 로그인이 진짜 호출이 되면서, 화면 테스트가 그대로면 매번 서버에
// 붙으려 한다. 여기서 응답을 정해 주고 화면이 어떻게 반응하는지만 본다.

import 'package:arda/api/api_error.dart';
import 'package:arda/auth/auth_service.dart';
import 'package:arda/models/app_user.dart';

/// 화면 테스트가 쓰는 기본 사용자.
final testUser = const AppUser(
  id: 1,
  email: 'test@example.com',
  name: '김민아',
  role: UserRole.member,
);

/// [AuthService] 를 흉내 낸다.
///
/// [error] 를 주면 로그인이 그것으로 실패한다 — 틀린 비밀번호와 끊긴 네트워크가
/// 다른 문구를 내는지 보려는 것이다.
class FakeAuthService implements AuthService {
  FakeAuthService({
    this.user,
    this.error,
    this.restored,
    this.delay = Duration.zero,
  });

  /// 로그인 성공 시 돌려줄 사용자
  final AppUser? user;

  /// 주면 로그인이 이걸 던진다
  final ApiError? error;

  /// 앱을 켤 때 복구되는 사용자. null 이면 로그인 화면으로 간다
  final AppUser? restored;

  /// 보내는 중 상태(스피너·버튼 잠금)를 볼 수 있게 늦춘다
  final Duration delay;

  /// 로그아웃이 실제로 불렸는지
  bool loggedOut = false;

  @override
  Future<AppUser> login({
    required String email,
    required String password,
  }) async {
    if (delay > Duration.zero) await Future<void>.delayed(delay);
    if (error != null) throw error!;
    return user ?? testUser;
  }

  @override
  Future<AppUser?> restore() async => restored;

  @override
  Future<AppUser> me() async => user ?? testUser;

  @override
  Future<AppUser> updateMe({
    String? name,
    String? currentPassword,
    String? newPassword,
  }) async => user ?? testUser;

  @override
  Future<void> logout() async => loggedOut = true;

  // 화면은 client 를 쓰지 않는다 — 쓰게 되면 그때 가짜를 채운다
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// 이름만 바꾼 사본 — "로그인한 사람 이름이 뜬다" 를 확인할 때 쓴다.
extension TestUserName on AppUser {
  AppUser copyWithName(String newName) =>
      AppUser(id: id, email: email, name: newName, role: role);
}
