/// 저장소 묶음 — 화면이 서버 대신 가짜를 볼 수 있게 하는 통로.
///
/// 큐 8 에서 화면마다 저장소가 붙는데, 테스트가 가짜를 넣으려고 화면 인자를
/// [HomeShell] → [ArdaApp] 까지 줄줄이 뚫으면 인자가 계속 늘어난다.
/// 트리 위쪽에 하나 꽂아 두고 필요한 화면이 꺼내 쓴다.
///
/// **없으면 화면이 진짜를 만든다.** 앱을 그냥 띄우면 이 스코프가 없어도 돌아간다 —
/// 화면 하나만 따로 띄워 보는 개발 중에도 걸리지 않게.
library;

import 'package:flutter/widgets.dart';

import 'posting_repository.dart';

class Repositories {
  const Repositories({this.postings});

  final PostingRepository? postings;
}

class RepositoryScope extends InheritedWidget {
  const RepositoryScope({
    super.key,
    required this.repositories,
    required super.child,
  });

  final Repositories repositories;

  /// 화면 갱신을 일으키지 않고 꺼내기만 한다 — 저장소는 바뀌지 않는다
  static Repositories? of(BuildContext context) =>
      context.getInheritedWidgetOfExactType<RepositoryScope>()?.repositories;

  @override
  bool updateShouldNotify(RepositoryScope oldWidget) =>
      repositories != oldWidget.repositories;
}
