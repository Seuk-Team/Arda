// 첨부 파일 열기 — 큐 8 4단계 (2026-09-03).
//
// 서버가 S3 서명 URL 을 주고 앱은 그것만 브라우저로 넘긴다.
// **누를 때마다 새로 받는다** — 서명에 유효 시간이 있어 미리 챙겨 두면 만료된다.

import 'package:arda/api/api_error.dart';
import 'package:arda/data/mock_data.dart';
import 'package:arda/models/applicant.dart';
import 'package:arda/screens/applicant_detail_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_repos.dart';

/// 김도현 — 첨부 두 건(이력서·자기소개서)을 가진 목데이터
final dohyun = mockApplicants.firstWhere((a) => a.name == '김도현');

/// 박지훈 — 첨부가 없다(담당자 직접 등록, D6)
final jihoon = mockApplicants.firstWhere((a) => a.name == '박지훈');

/// 브라우저에 넘긴 주소를 받아 두는 가짜 — 테스트가 진짜 브라우저를 띄우면 안 된다
class FakeOpener {
  FakeOpener({this.result = true});

  final bool result;
  final opened = <String>[];

  Future<bool> call(String url) async {
    opened.add(url);
    return result;
  }
}

Future<void> open(
  WidgetTester tester,
  Applicant applicant, {
  required FakeApplicantRepository repo,
  required FakeOpener opener,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: ApplicantDetailScreen(
        applicant: applicant,
        postingTitle: mockPostings.first.title,
        repository: repo,
        openUrl: opener.call,
      ),
    ),
  );
  await tester.pumpAndSettle();
  await tester.ensureVisible(find.text('첨부 파일'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('누르면 그 파일의 주소를 받아 브라우저로 넘긴다', (tester) async {
    final repo = FakeApplicantRepository(
      applicants: [dohyun],
      fileUrl: 'https://example.com/signed/resume.pdf',
    );
    final opener = FakeOpener();
    await open(tester, dohyun, repo: repo, opener: opener);

    await tester.tap(find.text('김도현_이력서.pdf'));
    await tester.pumpAndSettle();

    final resume = mockFiles[dohyun.id]!.first;
    expect(repo.askedFileId, resume.id);
    expect(opener.opened, ['https://example.com/signed/resume.pdf']);
  });

  testWidgets('누를 때마다 새로 받는다 — 서명에 유효 시간이 있다', (tester) async {
    final repo = FakeApplicantRepository(applicants: [dohyun]);
    final opener = FakeOpener();
    await open(tester, dohyun, repo: repo, opener: opener);

    await tester.tap(find.text('김도현_이력서.pdf'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('김도현_이력서.pdf'));
    await tester.pumpAndSettle();

    expect(opener.opened.length, 2);
  });

  testWidgets('열 앱이 없으면 그렇게 말한다 — 아무 일 없는 것처럼 두지 않는다', (tester) async {
    final opener = FakeOpener(result: false);
    await open(
      tester,
      dohyun,
      repo: FakeApplicantRepository(applicants: [dohyun]),
      opener: opener,
    );

    await tester.tap(find.text('김도현_이력서.pdf'));
    await tester.pumpAndSettle();

    expect(find.text('이 파일을 열 수 있는 앱이 없습니다'), findsOneWidget);
  });

  testWidgets('주소를 못 받으면 서버 문구를 띄우고 브라우저는 안 연다', (tester) async {
    final opener = FakeOpener();
    await open(
      tester,
      dohyun,
      // 상세는 정상이고 첨부 주소만 실패한다 — 파일이 지워졌거나 권한이 없을 때
      repo: FakeApplicantRepository(
        applicants: [dohyun],
        fileError: const NetworkError(),
      ),
      opener: opener,
    );

    await tester.tap(find.text('김도현_이력서.pdf'));
    await tester.pumpAndSettle();

    expect(find.textContaining('네트워크를 확인'), findsOneWidget);
    expect(opener.opened, isEmpty);
  });

  testWidgets('첨부가 없으면 누를 것도 없다', (tester) async {
    final opener = FakeOpener();
    await open(
      tester,
      jihoon,
      repo: FakeApplicantRepository(applicants: [jihoon]),
      opener: opener,
    );

    expect(find.text('첨부된 파일이 없습니다.'), findsOneWidget);
    expect(opener.opened, isEmpty);
  });
}
