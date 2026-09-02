// 웹에는 있고 앱에 없던 것들 — 2026-09-02 에 옮긴 분.
// 공고 등록 · 공고별 검색 · 첨부 파일 · 비밀번호 변경 · 설정 로그아웃 · 제안 만료 칩.

import 'package:arda/data/mock_data.dart';
import 'package:arda/models/applicant.dart';
import 'package:arda/models/applicant_file.dart';
import 'package:arda/models/interview.dart';
import 'package:arda/models/job_posting.dart';
import 'package:arda/screens/applicant_detail_screen.dart';
import 'package:arda/screens/applicants_screen.dart';
import 'package:arda/screens/posting_new_screen.dart';
import 'package:arda/screens/settings_screen.dart';
import 'package:arda/theme/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_repos.dart';

final dohyun = mockApplicants.firstWhere((a) => a.name == '김도현');
final jihoon = mockApplicants.firstWhere((a) => a.name == '박지훈');

Widget detail(Applicant a) => MaterialApp(
  home: ApplicantDetailScreen(
    applicant: a,
    postingTitle: mockPostings.first.title,
  ),
);

/// 상세는 SingleChildScrollView 라 자식이 전부 만들어져 있다 — 화면 밖일 뿐이라
/// ensureVisible 로 끌어오면 된다(ListView 처럼 드래그할 필요가 없다).
Future<void> openDetail(WidgetTester tester, Applicant applicant) async {
  await tester.pumpWidget(detail(applicant));
  await tester.ensureVisible(find.text('첨부 파일'));
  await tester.pumpAndSettle();
}

void main() {
  group('공고별 지원자 — 검색', () {
    Future<void> open(WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: ApplicantsScreen(
            posting: mockPostings.first,
            repository: FakeApplicantRepository(),
          ),
        ),
      );
      // 서버에서 받아 오므로 한 번 정착시켜야 목록이 그려진다 (큐 8)
      await tester.pumpAndSettle();
    }

    testWidgets('검색칸이 단계 탭보다 위에 있다', (tester) async {
      await open(tester);

      final search = find.widgetWithText(TextField, '검색어 입력');
      expect(search, findsOneWidget);
      expect(
        tester.getRect(search).top,
        lessThan(tester.getRect(find.text('지원 접수').first).top),
      );
    });

    testWidgets('이름으로 거른다', (tester) async {
      await open(tester);
      // 지원 접수 단계엔 박지훈뿐이라 그가 걸리는 검색과 안 걸리는 검색을 본다
      expect(find.text('박지훈'), findsOneWidget);

      await tester.enterText(find.byType(TextField), '박');
      await tester.pumpAndSettle();
      expect(find.text('박지훈'), findsOneWidget);

      await tester.enterText(find.byType(TextField), '없는이름');
      await tester.pumpAndSettle();
      expect(find.text('박지훈'), findsNothing);
    });

    testWidgets('빈 문구가 두 가지다 — 원래 없는 것과 걸러진 것', (tester) async {
      await open(tester);

      await tester.enterText(find.byType(TextField), '없는이름');
      await tester.pumpAndSettle();
      expect(find.text('조건에 맞는 지원자가 없습니다.'), findsOneWidget);
      expect(find.text('아직 지원자가 없습니다.'), findsNothing);
    });

    testWidgets('탭 숫자는 검색과 무관하게 전체를 센다', (tester) async {
      await open(tester);

      await tester.enterText(find.byType(TextField), '없는이름');
      await tester.pumpAndSettle();

      // 걸러도 "지원 접수 1" 이 그대로여야 이 공고에 몇 명인지 알 수 있다
      expect(find.text('1'), findsWidgets);
    });
  });

  group('첨부 파일', () {
    testWidgets('파일명 · 종류 · 크기를 적는다', (tester) async {
      await openDetail(tester, dohyun);

      expect(find.text('첨부 파일'), findsOneWidget);
      expect(find.text('김도현_이력서.pdf'), findsOneWidget);
      expect(find.text('이력서 · 240 KB'), findsOneWidget);
      expect(find.text('자기소개서 파일 · 88 KB'), findsOneWidget);
    });

    testWidgets('없으면 블록은 남기고 그 사실을 적는다', (tester) async {
      await openDetail(tester, jihoon);

      // 블록째 사라지면 "아직 안 붙었나" 와 "원래 없다" 가 구별되지 않는다
      expect(find.text('첨부 파일'), findsOneWidget);
      expect(find.text('첨부된 파일이 없습니다.'), findsOneWidget);
    });

    testWidgets('지원 정보 다음, 메일 앞 — 웹과 같은 자리', (tester) async {
      await openDetail(tester, dohyun);

      final files = tester.getRect(find.text('첨부 파일')).top;
      expect(tester.getRect(find.text('지원 정보')).top, lessThan(files));
      expect(files, lessThan(tester.getRect(find.text('메일')).top));
    });

    test('크기 표기는 웹 fmtBytes 와 같다', () {
      ApplicantFile f(int bytes) => ApplicantFile(
        id: 1,
        applicationId: 1,
        filename: 'x.pdf',
        kind: FileKind.resume,
        sizeBytes: bytes,
        contentType: 'application/pdf',
        createdAt: DateTime(2026, 9, 1),
      );

      expect(f(512).sizeLabel, '512 B');
      expect(f(245760).sizeLabel, '240 KB');
      expect(f(1887437).sizeLabel, '1.8 MB');
    });
  });

  group('설정', () {
    /// 내 계정 탭은 ListView 라 화면 밖 항목이 만들어지지 않는다.
    /// 비밀번호 변경·로그아웃은 접힌 아래에 있어 내려야 보인다.
    Future<void> open(WidgetTester tester) async {
      await tester.pumpWidget(const MaterialApp(home: SettingsScreen()));
      await tester.dragUntilVisible(
        find.text('로그아웃'),
        find.byType(Scrollable).last,
        const Offset(0, -200),
      );
      await tester.pumpAndSettle();
    }

    testWidgets('비밀번호 변경 칸 셋 + [변경]', (tester) async {
      await open(tester);

      expect(find.text('비밀번호 변경'), findsOneWidget);
      for (final label in ['현재 비밀번호', '새 비밀번호', '새 비밀번호 확인']) {
        expect(find.text(label), findsOneWidget);
      }
      expect(find.text('변경'), findsOneWidget);
    });

    testWidgets('로그아웃만 살아 있다 — 나머지는 잠겨 있다', (tester) async {
      await open(tester);

      final logout = find.ancestor(
        of: find.text('로그아웃'),
        matching: find.byType(InkWell),
      );
      expect(tester.widget<InkWell>(logout.first).onTap, isNotNull);

      // 저장·변경은 눌러도 아무 일이 없다
      for (final label in ['저장', '변경']) {
        final btn = find.ancestor(
          of: find.text(label),
          matching: find.byType(InkWell),
        );
        if (btn.evaluate().isNotEmpty) {
          expect(
            tester.widget<InkWell>(btn.first).onTap,
            isNull,
            reason: '$label 이 눌린다',
          );
        }
      }
    });

    testWidgets('로그아웃이 비밀번호 변경보다 아래 — 마지막 구획이다', (tester) async {
      await open(tester);

      expect(
        tester.getRect(find.text('비밀번호 변경')).top,
        lessThan(tester.getRect(find.text('로그아웃')).top),
      );
    });
  });

  group('공고 등록', () {
    Future<void> open(WidgetTester tester) async {
      await tester.pumpWidget(const MaterialApp(home: PostingNewScreen()));
    }

    testWidgets('공고명이 비면 [등록] 이 잠긴다', (tester) async {
      await open(tester);

      final submit = find.widgetWithText(FilledButton, '등록');
      expect(tester.widget<FilledButton>(submit).onPressed, isNull);

      await tester.enterText(find.byType(TextField), '백엔드 개발자');
      await tester.pumpAndSettle();
      expect(tester.widget<FilledButton>(submit).onPressed, isNotNull);
    });

    testWidgets('마감일은 비워 둘 수 있다 — 상시 채용', (tester) async {
      await open(tester);

      expect(find.text('연도-월-일'), findsOneWidget);
      expect(find.text('비우면 상시 채용이 된다.'), findsOneWidget);
    });

    testWidgets('상태 셋이 다 보이고 진행중이 기본이다', (tester) async {
      await open(tester);

      for (final s in PostingStatus.values) {
        expect(find.text(s.label), findsOneWidget);
      }

      // §1: 고른 것만 잎초록, 나머지는 무채
      final open_ = tester.widget<Text>(find.text(PostingStatus.open.label));
      expect(open_.style!.color, AppColors.leaf);
      final draft = tester.widget<Text>(find.text(PostingStatus.draft.label));
      expect(draft.style!.color, AppColors.textSub);
    });

    testWidgets('아직 저장되지 않는다 — 누르면 그렇게 말한다', (tester) async {
      // [등록] 은 토스트를 띄우고 화면을 닫는다. 돌아갈 화면이 없으면 토스트까지
      // 같이 사라지므로, 실제처럼 밀어 올린 뒤에 확인한다
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (c) => Scaffold(
              body: TextButton(
                onPressed: () => Navigator.push(
                  c,
                  MaterialPageRoute(builder: (_) => const PostingNewScreen()),
                ),
                child: const Text('열기'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('열기'));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), '백엔드 개발자');
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, '등록'));
      await tester.pumpAndSettle();

      expect(find.textContaining('아직 저장되지 않음'), findsOneWidget);
    });
  });

  group('일정 제안 상태', () {
    test('세 상태를 목데이터가 다 갖는다', () {
      expect(mockScheduleStatus[2], ScheduleStatus.proposed);
      expect(mockScheduleStatus[6], ScheduleStatus.expired);
      // 없는 사람은 "일정 없음"
      expect(mockScheduleStatus[3], isNull);
    });

    test('문구는 웹 Dashboard.tsx 그대로', () {
      expect(ScheduleStatus.none.label, '일정 없음');
      expect(ScheduleStatus.proposed.label, '일정 제안 중');
      expect(ScheduleStatus.expired.label, '제안 만료');
    });
  });
}
