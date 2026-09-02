// 공고 목록 — 큐 8 에서 서버로 바뀐 첫 화면.
// 05-design §6 세 상태(로딩·빈·오류)가 여기서부터 실제로 확인 가능해진다.

import 'package:arda/api/api_error.dart';
import 'package:arda/data/posting_repository.dart';
import 'package:arda/models/job_posting.dart';
import 'package:arda/screens/postings_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_repos.dart';

void main() {
  Widget host(PostingRepository repo) => MaterialApp(
    home: Scaffold(body: PostingsScreen(repository: repo)),
  );

  group('세 상태 (§6)', () {
    testWidgets('불러오는 동안 "불러오는 중…"', (tester) async {
      await tester.pumpWidget(
        host(FakePostingRepository(delay: const Duration(milliseconds: 200))),
      );
      await tester.pump();

      expect(find.text('불러오는 중…'), findsOneWidget);
      await tester.pumpAndSettle();
    });

    testWidgets('비면 웹과 같은 문구', (tester) async {
      await tester.pumpWidget(host(FakePostingRepository(postings: const [])));
      await tester.pumpAndSettle();

      expect(find.text('등록된 공고가 없습니다.'), findsOneWidget);
    });

    testWidgets('실패하면 서버 문구 + [다시 시도] — 앱엔 F5 가 없다', (tester) async {
      await tester.pumpWidget(
        host(FakePostingRepository(error: const NetworkError())),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('네트워크를 확인'), findsOneWidget);
      expect(find.text('다시 시도'), findsOneWidget);
    });

    testWidgets('[다시 시도] 는 다시 부른다 — 실패한 Future 를 재사용하지 않는다', (tester) async {
      var calls = 0;
      final repo = _CountingRepository(() => calls++);

      await tester.pumpWidget(host(repo));
      await tester.pumpAndSettle();
      expect(calls, 1);

      await tester.tap(find.text('다시 시도'));
      await tester.pumpAndSettle();
      expect(calls, 2);
    });
  });

  testWidgets('받아온 공고를 카드로 그린다', (tester) async {
    await tester.pumpWidget(host(FakePostingRepository()));
    await tester.pumpAndSettle();

    expect(find.text('백엔드 개발자 (신입)'), findsOneWidget);
  });

  group('JSON 파싱', () {
    test('PostingOut 을 판다', () {
      final p = JobPostingJson.fromJson({
        'id': 7,
        'title': '백엔드 개발자',
        'status': 'open',
        'deadline': '2026-09-09',
        'application_count': 6,
      });

      expect(p.id, 7);
      expect(p.title, '백엔드 개발자');
      expect(p.status, PostingStatus.open);
      expect(p.deadline, DateTime(2026, 9, 9));
    });

    test('마감일이 없으면 상시 접수다', () {
      final p = JobPostingJson.fromJson({
        'id': 1,
        'title': '상시',
        'status': 'open',
        'deadline': null,
      });

      expect(p.deadline, isNull);
      expect(p.deadlineLabel(DateTime(2026, 9, 2)), isNull);
    });

    test('모르는 상태는 작성 중으로 — 진행중으로 넘겨짚지 않는다', () {
      final p = JobPostingJson.fromJson({
        'id': 1,
        'title': 'x',
        'status': 'archived',
      });

      // 진행중으로 보이면 지원 링크가 열려 있는 것처럼 읽힌다
      expect(p.status, PostingStatus.draft);
    });
  });
}

/// 부른 횟수를 센다 — [다시 시도] 가 진짜로 다시 부르는지 보려는 것
class _CountingRepository implements PostingRepository {
  _CountingRepository(this.onCall);

  final void Function() onCall;

  @override
  Future<List<PostingWithCounts>> list() async {
    onCall();
    // 한 틱 미룬다 — 즉시 던지면 FutureBuilder 가 붙기 전에 실패해서
    // 테스트 프레임워크가 잡히지 않은 예외로 본다. 실제 네트워크도 즉시
    // 실패하지는 않는다
    await Future<void>.delayed(Duration.zero);
    throw const NetworkError();
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
