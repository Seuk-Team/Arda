// 더보기 — 탭 5칸에 못 들어간 메뉴와 프로필이 모이는 화면.
// 05-design 설정 절이 프로필에 정한 것(표시 전용·사진 없음)을 지키는지가 핵심이다.

import 'package:arda/data/mock_data.dart';
import 'package:arda/models/app_user.dart';
import 'package:arda/screens/more_screen.dart';
import 'package:arda/theme/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Widget host({AppUser? user, int? reviewCount}) => MaterialApp(
  home: Scaffold(
    body: MoreScreen(user: user, reviewCount: reviewCount),
  ),
);

void main() {
  testWidgets('프로필은 이니셜 아바타 + 이름 + 역할 — 사진은 없다', (tester) async {
    await tester.pumpWidget(host());

    expect(find.text(mockUser.name), findsOneWidget);
    expect(find.text('김'), findsOneWidget, reason: '이니셜');
    expect(find.textContaining(mockUser.role.label), findsOneWidget);
    // users 테이블에 사진 컬럼이 없다 — 이미지 위젯이 있으면 안 된다
    expect(find.byType(Image), findsNothing);
  });

  testWidgets('프로필은 표시 전용 — 누를 수 없다 (05-design 설정 절)', (tester) async {
    await tester.pumpWidget(host());

    final tappable = find.ancestor(
      of: find.text(mockUser.name),
      matching: find.byType(InkWell),
    );
    expect(tappable, findsNothing);
  });

  testWidgets('역할 라벨은 웹 ROLE_LABEL 과 같다', (tester) async {
    expect(UserRole.admin.label, '관리자');
    expect(UserRole.member.label, '멤버');

    await tester.pumpWidget(
      host(
        user: const AppUser(
          id: 9,
          email: 'boss@arda.team',
          name: '박관리',
          role: UserRole.admin,
        ),
      ),
    );
    expect(find.textContaining('관리자'), findsOneWidget);
  });

  testWidgets('탭에 못 들어간 메뉴가 여기 있다 — 평가 현황 · 설정', (tester) async {
    await tester.pumpWidget(host());

    expect(find.text('평가 현황'), findsOneWidget);
    expect(find.text('설정'), findsOneWidget);
  });

  testWidgets('평가 대기 건수가 배지로 붙는다', (tester) async {
    await tester.pumpWidget(host(reviewCount: 7));
    expect(find.text('7'), findsOneWidget);
  });

  testWidgets('대기 0건이면 배지를 그리지 않는다', (tester) async {
    await tester.pumpWidget(host(reviewCount: 0));
    expect(find.text('0'), findsNothing);
  });

  testWidgets('로그아웃만 적갈 — 되돌리기 어려운 항목 (§1)', (tester) async {
    await tester.pumpWidget(host());

    final logout = tester.widget<Text>(find.text('로그아웃'));
    expect(logout.style!.color, AppColors.danger);

    final settings = tester.widget<Text>(find.text('설정'));
    expect(settings.style!.color, AppColors.text);
  });

  testWidgets('로그아웃에는 화살표를 달지 않는다 — 이동이 아니라 실행이다', (tester) async {
    await tester.pumpWidget(host());

    // 화살표는 화면을 여는 항목에만 (평가 현황·단계 이력·설정·알림 = 4개)
    expect(find.byIcon(Icons.chevron_right), findsNWidgets(4));
  });

  testWidgets('목록 항목 높이가 터치 타깃 44 를 넘는다 (§9)', (tester) async {
    await tester.pumpWidget(host());

    for (final label in ['평가 현황', '단계 이력', '설정', '알림', '로그아웃']) {
      final row = tester.getSize(
        find
            .ancestor(of: find.text(label), matching: find.byType(InkWell))
            .first,
      );
      expect(
        row.height,
        greaterThanOrEqualTo(AppLayout.minTouchTarget),
        reason: label,
      );
    }
  });
}
