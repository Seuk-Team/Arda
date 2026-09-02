/// 로그인한 사람을 화면들이 함께 보는 자리.
///
/// 더보기·설정이 각자 `GET /auth/me` 를 부르면 탭을 옮길 때마다 같은 요청이
/// 나간다. 로그인·시작 화면에서 한 번 받아 여기 두고, 필요한 화면이 꺼내 쓴다.
///
/// 상태 관리 패키지를 들이지 않는다 — 앱 전체가 공유하는 값이 이것 하나뿐이라
/// `InheritedNotifier` 로 충분하다. 큐 8에서 공유할 것이 늘면 그때 다시 본다.
library;

import 'package:flutter/material.dart';

import '../models/app_user.dart';

class CurrentUser extends ValueNotifier<AppUser?> {
  CurrentUser([super.value]);
}

/// 트리 위쪽에 하나 꽂아 두고 아래 화면들이 [of] 로 읽는다.
///
/// 인증 서비스도 같이 들고 있다 — 로그아웃처럼 화면 깊은 곳에서 부르는 것이
/// 앱이 쓰는 것과 **같은** 서비스를 써야 한다. 각자 새로 만들면 테스트가 넣은
/// 가짜가 무시되고, 진짜 Keystore 를 두드린다.
class CurrentUserScope extends InheritedNotifier<CurrentUser> {
  const CurrentUserScope({
    super.key,
    required CurrentUser super.notifier,
    required super.child,
    this.auth,
  });

  /// 앱이 만든(또는 테스트가 넣은) 인증 서비스. null 이면 부르는 쪽이 만든다
  final Object? auth;

  /// 화면 갱신 없이 서비스만 꺼낸다
  static Object? authOf(BuildContext context) =>
      context.getInheritedWidgetOfExactType<CurrentUserScope>()?.auth;

  /// 로그인 전이거나(시작 화면) 아직 못 받았으면 null 이다.
  /// 화면은 목데이터로 떨어지지 않고 **모르는 채로 그린다** — 없는 이름을
  /// 지어내면 남의 계정처럼 보인다
  static AppUser? of(BuildContext context) => context
      .dependOnInheritedWidgetOfExactType<CurrentUserScope>()
      ?.notifier
      ?.value;

  /// 값을 넣는 쪽. 화면 갱신을 일으키지 않고 참조만 가져온다
  static CurrentUser? notifierOf(BuildContext context) =>
      context.getInheritedWidgetOfExactType<CurrentUserScope>()?.notifier;
}
