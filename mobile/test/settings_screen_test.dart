// 설정 — 배포판 웹의 탭 4개를 앱으로 옮긴 것.
// 지금은 전부 잠긴 화면이라 "살아 있는 것처럼 보이지 않는가"가 검사 대상이다.

import 'package:arda/data/mock_data.dart';
import 'package:arda/models/app_user.dart';
import 'package:arda/screens/settings_screen.dart';
import 'package:arda/theme/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Widget host({AppUser? user}) =>
    MaterialApp(home: SettingsScreen(user: user));

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

  testWidgets('내 계정은 잠겨 있다 — 배포판과 같은 문구', (tester) async {
    await tester.pumpWidget(host());

    expect(find.text('내 정보 수정 API가 아직 없어 저장할 수 없습니다.'), findsOneWidget);
    // 살아 있는 입력칸이 없다 — 있으면 고칠 수 있는 것처럼 보인다
    expect(find.byType(TextField), findsNothing);
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
      find.byType(Scrollable).last,
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

  testWidgets('메일 템플릿 — 단계를 고르면 안내 문구가 따라 바뀐다', (tester) async {
    await tester.pumpWidget(host());
    await openTab(tester, SettingsTab.mail);

    expect(find.text('서류 검토 단계 메일 문구는 아직 확정 전입니다.'), findsOneWidget);

    await tester.tap(find.text('불합격'));
    await tester.pumpAndSettle();
    expect(find.text('불합격 단계 메일 문구는 아직 확정 전입니다.'), findsOneWidget);
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
        find.ancestor(of: find.text(tab.label), matching: find.byType(InkWell)).first,
      );
      expect(box.height, greaterThanOrEqualTo(AppLayout.minTouchTarget), reason: tab.label);
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
