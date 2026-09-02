/// 로그아웃 — 더보기와 설정 두 곳에서 부른다.
///
/// 웹도 우측 상단과 설정 두 자리에 두므로 앱도 같다. 대신 **하는 일은 한 곳에**
/// 둔다 — 한쪽만 토큰을 지우고 다른 쪽은 화면만 넘기면, 나간 줄 알았는데 다음에
/// 켤 때 그대로 들어가진다.
library;

import 'package:flutter/material.dart';

import '../routes.dart';
import 'auth_service.dart';
import 'current_user.dart';

/// 토큰을 지우고 공유 사용자를 비운 뒤 로그인 화면으로 보낸다.
///
/// 스택을 통째로 비운다 — 뒤로가기로 앱 안에 다시 들어오면 안 된다.
/// 서버에 알릴 것은 없다: 상태를 갖지 않는 JWT 라 로그아웃 엔드포인트가 없다.
Future<void> logout(BuildContext context, {AuthService? auth}) async {
  final navigator = Navigator.of(context);
  final user = CurrentUserScope.notifierOf(context);
  // 앱이 쓰는 서비스를 그대로 쓴다 — 여기서 새로 만들면 테스트가 넣은 가짜가
  // 무시되고 진짜 Keystore 를 두드린다
  final service =
      auth ?? CurrentUserScope.authOf(context) as AuthService? ?? AuthService();

  // 화면부터 넘긴다. 토큰 지우기가 늦거나 실패해도 나가는 것은 되어야 한다 —
  // 눌렀는데 아무 일이 없으면 사용자는 로그아웃할 방법이 없다
  user?.value = null;
  navigator.pushNamedAndRemoveUntil(Routes.login, (_) => false);

  await service.logout();
}
