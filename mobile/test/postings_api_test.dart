// 공고 목록 — 큐 8 에서 서버로 바뀐 첫 화면.
// 05-design §6 세 상태(로딩·빈·오류)가 여기서부터 실제로 확인 가능해진다.

import 'package:arda/api/api_error.dart';
import 'package:arda/data/mock_data.dart';
import 'package:arda/data/posting_repository.dart';
import 'package:arda/data/repositories.dart';
import 'package:arda/screens/applicants_screen.dart';
import 'package:arda/models/job_posting.dart';
import 'package:arda/theme/tokens.dart';
import 'package:arda/utils/format.dart';
import 'package:arda/screens/posting_form_screen.dart';
import 'package:arda/screens/postings_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_repos.dart';

void main() {
  createTests();
  editTests();
  editPlumbingTests();
  deleteTests();

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

/// 공고 등록 — 큐 8 3단계(2026-09-03). **웹에는 아직 없는 동작이다.**
void createTests() {
  /// 실제처럼 목록 위에 밀어 올린다. 돌아갈 화면이 없으면 성공 토스트가
  /// 화면과 함께 사라져 확인할 수 없다
  Future<void> openNew(WidgetTester tester, FakePostingRepository repo) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (c) => Scaffold(
            body: TextButton(
              onPressed: () => Navigator.push(
                c,
                MaterialPageRoute(
                  builder: (_) => PostingFormScreen(repository: repo),
                ),
              ),
              child: const Text('열기'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('열기'));
    await tester.pumpAndSettle();
  }

  Future<void> fillAndSubmit(WidgetTester tester, String title) async {
    await tester.enterText(find.byType(TextField), title);
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, '등록'));
    await tester.pumpAndSettle();
  }

  group('공고 등록 — 저장', () {
    testWidgets('적은 값이 그대로 간다', (tester) async {
      final repo = FakePostingRepository();
      await openNew(tester, repo);
      await fillAndSubmit(tester, '백엔드 개발자 (신입)');

      expect(repo.createdTitle, '백엔드 개발자 (신입)');
      // 화면 기본값 — 만들자마자 지원을 받는 것이 가장 흔하다
      expect(repo.createdStatus, PostingStatus.open);
      // 마감일을 안 고르면 상시 채용이다
      expect(repo.createdDeadline, isNull);
    });

    testWidgets('앞뒤 공백은 떼고 보낸다', (tester) async {
      final repo = FakePostingRepository();
      await openNew(tester, repo);
      await fillAndSubmit(tester, '  프론트엔드 개발자  ');

      expect(repo.createdTitle, '프론트엔드 개발자');
    });

    testWidgets('고른 상태가 함께 간다', (tester) async {
      final repo = FakePostingRepository();
      await openNew(tester, repo);

      await tester.tap(find.text(PostingStatus.draft.label));
      await tester.pumpAndSettle();
      await fillAndSubmit(tester, '작성 중인 공고');

      expect(repo.createdStatus, PostingStatus.draft);
    });

    testWidgets('성공하면 목록으로 돌아가며 그렇게 말한다 (§6)', (tester) async {
      await openNew(tester, FakePostingRepository());
      await fillAndSubmit(tester, '백엔드 개발자');

      expect(find.textContaining('공고를 등록했습니다'), findsOneWidget);
      // 화면이 닫혔다 — 등록 화면이 아니라 원래 자리다
      expect(find.byType(PostingFormScreen), findsNothing);
      // 예전의 "아직 저장되지 않음" 은 사라져야 한다
      expect(find.textContaining('아직 저장되지 않음'), findsNothing);
    });

    testWidgets('보내는 동안 버튼이 잠긴다 — 두 번 누르면 공고가 두 개 생긴다', (tester) async {
      final repo = FakePostingRepository(
        createDelay: const Duration(milliseconds: 300),
      );
      await openNew(tester, repo);

      await tester.enterText(find.byType(TextField), '백엔드 개발자');
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, '등록'));
      await tester.pump(); // 보내기 시작

      // 글자를 지우지 않고 그 자리에 스피너를 둔다(단계 변경과 같은 방식)
      expect(find.byType(CircularProgressIndicator), findsWidgets);
      expect(find.widgetWithText(FilledButton, '등록'), findsNothing);

      await tester.pumpAndSettle();
    });

    testWidgets('실패하면 화면을 닫지 않는다 — 적은 것이 사라지면 안 된다', (tester) async {
      final repo = FakePostingRepository(createError: const NetworkError());
      await openNew(tester, repo);
      await fillAndSubmit(tester, '지우면 안 되는 공고명');

      expect(find.textContaining('네트워크를 확인'), findsOneWidget);
      expect(find.byType(PostingFormScreen), findsOneWidget);
      expect(find.text('지우면 안 되는 공고명'), findsOneWidget);
    });

    testWidgets('서버가 거절하면 그 이유를 그대로 보여 준다', (tester) async {
      final repo = FakePostingRepository(
        // 지난 날짜로 마감을 걸면 서버가 422 로 막는다 (02-api.md)
        createError: const ServerError(422, '마감일은 오늘 이후여야 합니다.'),
      );
      await openNew(tester, repo);
      await fillAndSubmit(tester, '백엔드 개발자');

      expect(find.text('마감일은 오늘 이후여야 합니다.'), findsOneWidget);
    });

    testWidgets('공고명은 200자까지만 들어간다 — 넘겨 보내 422 를 받지 않는다', (tester) async {
      final repo = FakePostingRepository();
      await openNew(tester, repo);
      await fillAndSubmit(tester, '가' * 250);

      expect(repo.createdTitle!.length, 200);
    });
  });

  group('등록 뒤 목록', () {
    testWidgets('새로 받는다 — 그대로면 방금 만든 공고가 안 보인다', (tester) async {
      final repo = FakePostingRepository();
      final reload = ValueNotifier(0);

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: PostingsScreen(repository: repo, reloadSignal: reload),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(repo.listCalls, 1);

      // [+] 가 성공하고 돌아온 상황
      reload.value++;
      await tester.pumpAndSettle();

      expect(repo.listCalls, 2);
    });
  });
}

/// 공고 수정 — `PATCH /postings/{id}` (2026-09-03). 웹에도 없는 화면이다.
void editTests() {
  final existing = JobPosting(
    id: 42,
    title: '백엔드 개발자 (신입)',
    status: PostingStatus.open,
    deadline: DateTime.now().add(const Duration(days: 30)),
  );

  Future<void> openEdit(
    WidgetTester tester,
    FakePostingRepository repo, {
    JobPosting? posting,
  }) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (c) => Scaffold(
            body: TextButton(
              onPressed: () => Navigator.push(
                c,
                MaterialPageRoute(
                  builder: (_) => PostingFormScreen(
                    posting: posting ?? existing,
                    repository: repo,
                  ),
                ),
              ),
              child: const Text('열기'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('열기'));
    await tester.pumpAndSettle();
  }

  group('공고 수정 — 화면', () {
    testWidgets('지금 값이 채워져 있다 — 빈 칸에서 시작하면 다시 다 적어야 한다', (tester) async {
      await openEdit(tester, FakePostingRepository());

      expect(find.text('백엔드 개발자 (신입)'), findsOneWidget);
      expect(find.text(formatDate(existing.deadline!)), findsOneWidget);
      // 지금 상태가 골라져 있다
      final chip = tester.widget<Text>(find.text(PostingStatus.open.label));
      expect(chip.style!.color, AppColors.leaf);
    });

    testWidgets('제목과 버튼 글자가 등록과 다르다', (tester) async {
      await openEdit(tester, FakePostingRepository());

      expect(find.text('공고 수정'), findsOneWidget);
      // 이미 있는 공고에 "등록" 이 붙어 있으면 새로 만드는 줄 안다
      expect(find.widgetWithText(FilledButton, '저장'), findsOneWidget);
      expect(find.widgetWithText(FilledButton, '등록'), findsNothing);
    });
  });

  group('공고 수정 — 저장', () {
    testWidgets('고친 제목이 그 공고 id 로 간다', (tester) async {
      final repo = FakePostingRepository();
      await openEdit(tester, repo);

      await tester.enterText(find.byType(TextField), '백엔드 개발자 (경력)');
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, '저장'));
      await tester.pumpAndSettle();

      expect(repo.updatedId, 42);
      expect(repo.updatedTitle, '백엔드 개발자 (경력)');
      expect(find.textContaining('공고를 수정했습니다'), findsOneWidget);
    });

    testWidgets('마감일을 안 건드리면 보내지 않는다', (tester) async {
      final repo = FakePostingRepository();
      await openEdit(tester, repo);

      await tester.enterText(find.byType(TextField), '제목만 고친다');
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, '저장'));
      await tester.pumpAndSettle();

      // PATCH 는 보낸 열쇠만 고친다. 안 건드린 마감일을 되보낼 이유가 없다
      expect(repo.updatedChangeDeadline, isFalse);
    });

    testWidgets('마감이 지난 공고도 제목을 고칠 수 있다 — 되보내면 서버가 422 로 막는다', (tester) async {
      final repo = FakePostingRepository();
      final closed = JobPosting(
        id: 43,
        title: '작년 공고',
        status: PostingStatus.closed,
        deadline: DateTime.now().subtract(const Duration(days: 100)),
      );
      await openEdit(tester, repo, posting: closed);

      await tester.enterText(find.byType(TextField), '작년 공고 (수정)');
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, '저장'));
      await tester.pumpAndSettle();

      // 지난 날짜를 보내면 `_reject_past` 가 막아 제목조차 못 고친다
      expect(repo.updatedChangeDeadline, isFalse);
      expect(repo.updatedTitle, '작년 공고 (수정)');
    });

    testWidgets('마감일을 지우면 null 을 명시해 보낸다 — 상시로 바꾸라는 뜻이다', (tester) async {
      final repo = FakePostingRepository();
      await openEdit(tester, repo);

      await tester.tap(find.bySemanticsLabel('마감일 지우기'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, '저장'));
      await tester.pumpAndSettle();

      // 안 보내면 서버가 그대로 두므로 상시로 못 바꾼다
      expect(repo.updatedChangeDeadline, isTrue);
      expect(repo.updatedDeadline, isNull);
    });

    testWidgets('실패하면 화면을 닫지 않는다', (tester) async {
      final repo = FakePostingRepository(createError: const NetworkError());
      await openEdit(tester, repo);

      await tester.tap(find.widgetWithText(FilledButton, '저장'));
      await tester.pumpAndSettle();

      expect(find.textContaining('네트워크를 확인'), findsOneWidget);
      expect(find.byType(PostingFormScreen), findsOneWidget);
    });
  });
}

/// 고친 결과가 화면들에 닿는지 — 헤더와 목록 (2026-09-03).
void editPlumbingTests() {
  final posting = mockPostings.first;

  group('수정 결과가 화면에 닿는다', () {
    testWidgets('지원자 화면 헤더가 새 제목으로 바뀐다', (tester) async {
      final postingRepo = FakePostingRepository();

      await tester.pumpWidget(
        RepositoryScope(
          repositories: Repositories(
            postings: postingRepo,
            applicants: FakeApplicantRepository(),
          ),
          child: MaterialApp(
            home: ApplicantsScreen(
              posting: posting,
              repository: FakeApplicantRepository(),
            ),
            onGenerateRoute: (settings) => MaterialPageRoute(
              settings: settings,
              builder: (_) => PostingFormScreen(
                posting: settings.arguments! as JobPosting,
                repository: postingRepo,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text(posting.title), findsOneWidget);

      // 상단 바 [✎] 로 들어가 제목을 고친다
      await tester.tap(find.bySemanticsLabel('공고 수정'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).first, '이름 바꾼 공고');
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, '저장'));
      await tester.pumpAndSettle();

      // 돌아온 헤더가 새 제목이다 — 원래 제목이 남아 있으면 저장이 안 된 줄 안다
      expect(find.text('이름 바꾼 공고'), findsOneWidget);
      expect(find.text(posting.title), findsNothing);
    });

    testWidgets('안 고치고 나오면 목록에 헛걸음시키지 않는다', (tester) async {
      Object? popped;

      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (c) => Scaffold(
              body: TextButton(
                onPressed: () async {
                  popped = await Navigator.push(
                    c,
                    MaterialPageRoute(
                      builder: (_) => ApplicantsScreen(
                        posting: posting,
                        repository: FakeApplicantRepository(),
                      ),
                    ),
                  );
                },
                child: const Text('열기'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('열기'));
      await tester.pumpAndSettle();

      await tester.tap(find.bySemanticsLabel('뒤로'));
      await tester.pumpAndSettle();

      // 공고를 안 건드렸으면 목록이 다시 받을 이유가 없다
      expect(popped, false);
    });
  });
}

/// 공고 삭제 (2026-09-03) — `DELETE /postings/{id}`.
///
/// 되돌릴 수 없는 동작이라 **확인 시트를 거치는지**가 이 묶음의 핵심이다.
/// 지원자가 딸린 공고는 서버가 409 로 막는다 — 앱은 그 문구를 그대로 띄운다.
void deleteTests() {
  final existing = JobPosting(
    id: 7,
    title: '백엔드 개발자 (신입)',
    status: PostingStatus.open,
    deadline: DateTime.now().add(const Duration(days: 30)),
  );

  /// 폼을 띄우고 [삭제] 가 보이는 데까지 스크롤한다.
  ///
  /// `find.byType(Scrollable).last` 를 쓰면 TextField 안쪽 스크롤을 집는다 —
  /// [ensureVisible] 로 위젯을 직접 지정한다.
  Future<void> openEdit(WidgetTester tester, FakePostingRepository repo) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (c) => Scaffold(
            body: TextButton(
              onPressed: () => Navigator.push(
                c,
                MaterialPageRoute(
                  builder: (_) =>
                      PostingFormScreen(posting: existing, repository: repo),
                ),
              ),
              child: const Text('열기'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('열기'));
    await tester.pumpAndSettle();
  }

  Future<void> tapDelete(WidgetTester tester) async {
    await tester.ensureVisible(find.text('공고 삭제'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('공고 삭제'));
    await tester.pumpAndSettle();
  }

  group('공고 삭제', () {
    testWidgets('등록 화면에는 없다 — 지울 것이 아직 없다', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: PostingFormScreen(repository: FakePostingRepository()),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('공고 삭제'), findsNothing);
    });

    testWidgets('한 번 눌러서는 안 지운다 — 확인 시트가 뜬다', (tester) async {
      final repo = FakePostingRepository();
      await openEdit(tester, repo);
      await tapDelete(tester);

      // 무엇이 지워지는지 이름이 시트에 있다
      expect(find.text('${existing.title} 삭제'), findsOneWidget);
      expect(find.textContaining('되돌릴 수 없습니다'), findsOneWidget);
      // 아직 아무것도 안 나갔다
      expect(repo.deletedId, isNull);
    });

    testWidgets('취소하면 아무 일도 안 일어난다', (tester) async {
      final repo = FakePostingRepository();
      await openEdit(tester, repo);
      await tapDelete(tester);

      await tester.tap(find.widgetWithText(OutlinedButton, '취소'));
      await tester.pumpAndSettle();

      expect(repo.deletedId, isNull);
      expect(find.byType(PostingFormScreen), findsOneWidget);
    });

    testWidgets('확인하면 지우고 화면을 닫는다', (tester) async {
      final repo = FakePostingRepository();
      await openEdit(tester, repo);
      await tapDelete(tester);

      await tester.tap(find.widgetWithText(FilledButton, '삭제'));
      await tester.pumpAndSettle();

      expect(repo.deletedId, existing.id);
      expect(find.byType(PostingFormScreen), findsNothing);
      expect(find.textContaining('공고를 삭제했습니다'), findsOneWidget);
    });

    testWidgets('지원자가 있으면 서버 문구를 그대로 띄우고 화면을 안 닫는다', (tester) async {
      final repo = FakePostingRepository(
        // backend/app/api/postings.py 가 실제로 돌려주는 문구
        deleteError: const ServerError(
          409,
          '지원서 3건이 있는 공고는 삭제할 수 없습니다. 먼저 공고를 마감하세요.',
        ),
      );
      await openEdit(tester, repo);
      await tapDelete(tester);

      await tester.tap(find.widgetWithText(FilledButton, '삭제'));
      await tester.pumpAndSettle();

      // 앱이 지어낸 문구가 아니라 서버가 센 숫자가 그대로 나와야 한다
      expect(find.textContaining('지원서 3건'), findsOneWidget);
      expect(find.byType(PostingFormScreen), findsOneWidget);
    });

    testWidgets('지우면 그 공고의 지원자 화면도 함께 닫힌다', (tester) async {
      final postingRepo = FakePostingRepository();
      Object? popped;

      await tester.pumpWidget(
        RepositoryScope(
          repositories: Repositories(
            postings: postingRepo,
            applicants: FakeApplicantRepository(),
          ),
          child: MaterialApp(
            home: Builder(
              builder: (c) => Scaffold(
                body: TextButton(
                  onPressed: () async {
                    popped = await Navigator.push(
                      c,
                      MaterialPageRoute(
                        builder: (_) => ApplicantsScreen(
                          posting: existing,
                          repository: FakeApplicantRepository(),
                        ),
                      ),
                    );
                  },
                  child: const Text('열기'),
                ),
              ),
            ),
            onGenerateRoute: (settings) => MaterialPageRoute(
              settings: settings,
              builder: (_) => PostingFormScreen(
                posting: settings.arguments! as JobPosting,
                repository: postingRepo,
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('열기'));
      await tester.pumpAndSettle();

      await tester.tap(find.bySemanticsLabel('공고 수정'));
      await tester.pumpAndSettle();
      await tapDelete(tester);
      await tester.tap(find.widgetWithText(FilledButton, '삭제'));
      await tester.pumpAndSettle();

      // 없어진 공고의 지원자 목록이 남아 있으면 안 된다
      expect(find.byType(ApplicantsScreen), findsNothing);
      // 목록에게는 "바뀌었다" 로 알린다 — 사라진 카드를 지우게 해야 한다
      expect(popped, true);
    });
  });
}
