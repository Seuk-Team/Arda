// 설정 — 배포판 웹의 탭 4개를 앱으로 옮긴 것.
// 지금은 전부 잠긴 화면이라 "살아 있는 것처럼 보이지 않는가"가 검사 대상이다.

import 'package:arda/data/mock_data.dart';
import 'package:arda/models/app_user.dart';
import 'package:arda/screens/settings_screen.dart';
import 'package:arda/theme/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_repos.dart';

Widget host({AppUser? user}) => MaterialApp(
  // 나머지 세 탭이 서버에서 받아 온다(큐 8 4단계) — 가짜를 물린다
  home: SettingsScreen(user: user, repository: FakeSettingsRepository()),
);

Future<void> openTab(WidgetTester tester, SettingsTab tab) async {
  await tester.tap(find.text(tab.label));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('탭 4개가 배포판 순서대로 있다', (tester) async {
    await tester.pumpWidget(host());

    expect(SettingsTab.values.map((t) => t.label).toList(), [
      '내 계정',
      '사용자·권한',
      '메일 템플릿',
      '면접 가능 시간',
    ]);
    for (final tab in SettingsTab.values) {
      expect(find.text(tab.label), findsOneWidget);
    }
  });

  testWidgets('처음엔 내 계정 — 이름·이메일·역할', (tester) async {
    await tester.pumpWidget(host());

    expect(find.text(mockUser.name), findsOneWidget);
    expect(find.text(mockUser.email), findsOneWidget);
    expect(find.text(mockUser.role.label), findsOneWidget);
  });

  testWidgets('내 계정만 잠금이 풀렸다 — 이메일·역할은 그대로다 (큐 8, 2026-09-03)', (tester) async {
    await tester.pumpWidget(host());

    // 이름은 살아 있는 칸이다 — PATCH /auth/me 가 받는 유일한 텍스트
    expect(find.byType(TextField), findsWidgets);
    // 이메일·역할은 서버가 아예 안 받는다(MeUpdate) — 잠긴 채로 둔다
    expect(find.text('이메일과 역할은 본인이 바꿀 수 없습니다.'), findsOneWidget);
    expect(find.text('내 정보 수정 API가 아직 없어 저장할 수 없습니다.'), findsNothing);
  });

  testWidgets('사용자·권한 — 웹 표를 카드로 폈다 (§9)', (tester) async {
    await tester.pumpWidget(host());
    await openTab(tester, SettingsTab.users);

    expect(find.text('김채용'), findsOneWidget);
    expect(find.text('admin@arda.com'), findsOneWidget);
    expect(find.text('활성'), findsWidgets);

    // 비활성 계정은 목록 맨 아래다 — ListView 는 화면 밖 자식을 만들지 않는다
    await tester.dragUntilVisible(
      find.text('한도윤'),
      find.byType(ListView).last,
      const Offset(0, -200),
    );
    await tester.pumpAndSettle();
    expect(find.text('비활성'), findsOneWidget);
  });

  testWidgets('관리자만 잎초록 — 멤버는 보조색 (§1)', (tester) async {
    await tester.pumpWidget(host());
    await openTab(tester, SettingsTab.users);

    final admin = tester.widget<Text>(find.text('관리자'));
    expect(admin.style!.color, AppColors.leaf);

    final member = tester.widget<Text>(find.text('멤버').first);
    expect(member.style!.color, AppColors.textSub);
  });

  testWidgets('메일 템플릿 — 서버 문구를 보여 준다 (큐 8 4단계, 2026-09-03)', (tester) async {
    await tester.pumpWidget(host());
    await openTab(tester, SettingsTab.mail);

    // 실제로 나가는 문구다 — 자동 발송도 이걸 쓴다
    expect(find.text('[아르다] 지원서가 접수되었습니다'), findsOneWidget);
    expect(find.text('기본 문구입니다. 고치려면 웹 설정에서 하세요.'), findsOneWidget);
    expect(find.text('단계를 바꿀 때 자동으로 나가는 메일도 이 문구를 씁니다.'), findsOneWidget);
  });

  testWidgets('메일 템플릿 — 단계를 고르면 문구가 바뀌고 고친 사람이 보인다', (tester) async {
    await tester.pumpWidget(host());
    await openTab(tester, SettingsTab.mail);

    await tester.tap(find.text('면접 안내'));
    await tester.pumpAndSettle();

    expect(find.text('[아르다] 면접 안내'), findsOneWidget);
    // 기본 문구가 아니면 누가 고쳤는지가 붙는다 (`source: custom`)
    expect(find.textContaining('김채용 님이 고친 문구입니다'), findsOneWidget);
  });

  testWidgets('면접 가능 시간 — 비어 있음 문구는 배포판 그대로', (tester) async {
    await tester.pumpWidget(host());
    await openTab(tester, SettingsTab.availability);

    expect(find.text('등록된 가능 시간이 없습니다.'), findsOneWidget);
    expect(find.textContaining('비워 두면 제안을 만들 수 없습니다'), findsOneWidget);
  });

  testWidgets('탭 줄은 터치 타깃 44 를 넘는다 (§9)', (tester) async {
    await tester.pumpWidget(host());

    for (final tab in SettingsTab.values) {
      final box = tester.getSize(
        find
            .ancestor(of: find.text(tab.label), matching: find.byType(InkWell))
            .first,
      );
      expect(
        box.height,
        greaterThanOrEqualTo(AppLayout.minTouchTarget),
        reason: tab.label,
      );
    }
  });

  testWidgets('역할별로 탭을 숨기지 않는다 — 막는 것은 서버 (ADR-0017)', (tester) async {
    await tester.pumpWidget(
      host(
        user: const AppUser(
          id: 9,
          email: 'member@arda.team',
          name: '멤버',
          role: UserRole.member,
        ),
      ),
    );

    // admin 전용 탭도 그대로 보인다
    expect(find.text('사용자·권한'), findsOneWidget);
    expect(find.text('메일 템플릿'), findsOneWidget);
  });
}
