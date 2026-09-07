// 평가 현황 — 05-design §6 의 세 상태 + 줄에 붙는 상태들.
//
// 문구는 웹(Evaluations.tsx)에서 가져온 것이라 글자 그대로 비교한다.
// 임계값(의견 갈림 2점·경과 3일)도 웹과 같아야 한다 — 여기서 못을 박는다.

import 'package:arda/data/mock_data.dart';
import 'package:arda/models/applicant.dart';
// flutter_test 도 Evaluation 을 내보낸다(접근성 검사) — 다른 평가 테스트와
// 같은 접두어를 쓴다
import 'package:arda/models/evaluation.dart' as model;
import 'package:arda/screens/evaluation_queue_screen.dart';
import 'package:arda/theme/tokens.dart';
import 'package:arda/utils/eval_queue.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Widget host(QueueLoader loader) =>
    MaterialApp(home: EvaluationQueueScreen(loader: loader));

/// 로그인한 사람 — [mockUser] 와 같은 id 를 쓴다
const meId = 1;

QueueEntry entryFor(
  int applicantId, {
  int assignedDaysAgo = 0,
  List<model.Evaluation> evaluations = const [],
  double? avgScore,
  String? postingTitle,
}) {
  final applicant = mockApplicants.firstWhere((a) => a.id == applicantId);
  final title =
      postingTitle ??
      mockPostings.firstWhere((p) => p.id == applicant.jobPostingId).title;
  return QueueEntry(
    applicant: applicant,
    postingTitle: title,
    assignedAt: DateTime.now().subtract(Duration(days: assignedDaysAgo)),
    evaluations: evaluations,
    avgScore: avgScore,
  );
}

model.Evaluation ev({
  required int id,
  required int evaluatorId,
  required int score,
  String? name,
}) => model.Evaluation(
  id: id,
  applicationId: 0,
  evaluatorId: evaluatorId,
  evaluatorName: name,
  score: score,
  createdAt: DateTime(2026, 9, 1),
);

/// 목데이터의 지원자는 전부 1번 공고 소속이라 그대로는 레일이 한 칸이다.
/// 공고를 갈아 끼워 여러 공고 상황을 만든다
QueueEntry entryOn(int applicantId, int postingId, String title) {
  final a = mockApplicants.firstWhere((x) => x.id == applicantId);
  return QueueEntry(
    applicant: Applicant(
      id: a.id,
      jobPostingId: postingId,
      name: a.name,
      email: a.email,
      currentStage: a.currentStage,
      createdAt: a.createdAt,
    ),
    postingTitle: title,
    assignedAt: DateTime.now(),
  );
}

QueueData data(List<QueueEntry> entries, {Map<int, String> names = const {}}) =>
    QueueData(entries: entries, evaluatorNames: names, meId: meId);

void main() {
  group('§6 로딩', () {
    testWidgets('불러오는 동안 문구 + 골격 카드', (tester) async {
      await tester.pumpWidget(
        host(
          () =>
              Future.delayed(const Duration(seconds: 1), () => data(const [])),
        ),
      );
      await tester.pump(); // 첫 프레임 — 아직 대기 중

      expect(find.text('불러오는 중…'), findsOneWidget);
      // 골격 3장 — 곧 무엇이 올지 자리로 알려 준다
      expect(find.byType(FractionallySizedBox), findsNWidgets(9));

      // 남은 타이머를 흘려보낸다 — 안 그러면 '보류 중인 타이머' 로 실패한다
      await tester.pump(const Duration(seconds: 1));
    });
  });

  group('§6 비어 있음', () {
    testWidgets('웹과 같은 문구', (tester) async {
      await tester.pumpWidget(host(() async => data(const [])));
      await tester.pumpAndSettle();

      expect(find.text('평가 대기 중인 지원자가 없습니다.'), findsOneWidget);
      expect(find.text('불러오는 중…'), findsNothing);
    });
  });

  group('§6 오류', () {
    testWidgets('웹 문구 + [다시 시도] — 앱엔 새로고침이 없다', (tester) async {
      await tester.pumpWidget(host(() async => throw Exception('boom')));
      await tester.pumpAndSettle();

      expect(find.text('평가 대기 목록을 불러오지 못했습니다'), findsOneWidget);
      expect(find.text('다시 시도'), findsOneWidget);
    });

    testWidgets('오류 문구는 적갈, 워시 배경 (§1)', (tester) async {
      await tester.pumpWidget(host(() async => throw Exception('boom')));
      await tester.pumpAndSettle();

      final message = tester.widget<Text>(find.text('평가 대기 목록을 불러오지 못했습니다'));
      expect(message.style!.color, AppColors.danger);

      final box = tester.widget<Container>(
        find
            .ancestor(
              of: find.text('평가 대기 목록을 불러오지 못했습니다'),
              matching: find.byType(Container),
            )
            .last,
      );
      expect((box.decoration! as BoxDecoration).color, AppColors.dangerSoft);
    });

    testWidgets('[다시 시도] 를 누르면 다시 부른다', (tester) async {
      var calls = 0;
      await tester.pumpWidget(
        host(() async {
          calls++;
          if (calls == 1) throw Exception('boom');
          return data([entryFor(4)]);
        }),
      );
      await tester.pumpAndSettle();
      expect(find.text('다시 시도'), findsOneWidget);

      await tester.tap(find.text('다시 시도'));
      await tester.pumpAndSettle();

      expect(calls, 2);
      expect(find.text('평가 대기 목록을 불러오지 못했습니다'), findsNothing);
      expect(find.text('정우진'), findsOneWidget);
    });

    testWidgets('[다시 시도] 는 터치 타깃 44 (§9)', (tester) async {
      await tester.pumpWidget(host(() async => throw Exception('boom')));
      await tester.pumpAndSettle();

      final size = tester.getSize(
        find
            .ancestor(of: find.text('다시 시도'), matching: find.byType(InkWell))
            .first,
      );
      expect(size.height, AppLayout.minTouchTarget);
      expect(size.width, greaterThanOrEqualTo(AppLayout.minTouchTarget));
    });
  });

  group('머리말', () {
    testWidgets('웹과 같은 문구 — 안 낸 것 / 배정', (tester) async {
      await tester.pumpWidget(
        host(
          () async => data([
            entryFor(4),
            entryFor(
              1,
              evaluations: [ev(id: 1, evaluatorId: meId, score: 4)],
              avgScore: 4,
            ),
          ]),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('내가 안 낸 평가 1건 / 배정 2건'), findsOneWidget);
    });
  });

  group('줄', () {
    testWidgets('이름 · 단계 · 배정 며칠째', (tester) async {
      await tester.pumpWidget(
        host(() async => data([entryFor(4, assignedDaysAgo: 2)])),
      );
      await tester.pumpAndSettle();

      expect(find.text('정우진'), findsOneWidget);
      expect(find.text('서류 검토 · 배정 2일째'), findsOneWidget);
    });

    testWidgets('아무도 안 냈으면 미착수 + [평가]', (tester) async {
      await tester.pumpWidget(host(() async => data([entryFor(4)])));
      await tester.pumpAndSettle();

      expect(find.text('미착수'), findsOneWidget);
      expect(find.text('평가'), findsOneWidget);
      // 평가가 없으면 아바타 자리는 비운다 — 오른쪽이 이미 '미착수'라고 말한다
      expect(find.text('평가 없음'), findsNothing);
    });

    testWidgets('남들만 냈으면 평균 + 몇 명 냈는지, 그래도 [평가]', (tester) async {
      await tester.pumpWidget(
        host(
          () async => data(
            [
              entryFor(
                4,
                evaluations: [
                  ev(id: 1, evaluatorId: 2, score: 4),
                  ev(id: 2, evaluatorId: 3, score: 4),
                ],
                avgScore: 4,
              ),
            ],
            names: const {2: '김채용', 3: '이서연'},
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('4.0'), findsOneWidget);
      expect(find.text('2명 제출'), findsOneWidget);
      expect(find.text('평가'), findsOneWidget);
    });

    testWidgets('내가 냈으면 점수는 초록, 버튼은 [보기]', (tester) async {
      await tester.pumpWidget(
        host(
          () async => data(
            [
              entryFor(
                4,
                evaluations: [ev(id: 1, evaluatorId: meId, score: 5)],
                avgScore: 5,
              ),
            ],
            names: const {meId: '김민아'},
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        tester.widget<Text>(find.text('5.0')).style!.color,
        AppColors.okText,
      );
      expect(find.text('보기'), findsOneWidget);
      expect(find.text('평가'), findsNothing);
    });

    testWidgets('2점 넘게 갈리면 양끝 점수 + [의견 갈림] + [조정]', (tester) async {
      await tester.pumpWidget(
        host(
          () async => data(
            [
              entryFor(
                4,
                evaluations: [
                  ev(id: 1, evaluatorId: meId, score: 5),
                  ev(id: 2, evaluatorId: 2, score: 2),
                ],
                avgScore: 3.5,
              ),
            ],
            names: const {meId: '김민아', 2: '김채용'},
          ),
        ),
      );
      await tester.pumpAndSettle();

      // 평균 3.5 하나만 적으면 "무난함" 으로 읽혀 갈린 사실이 지워진다
      expect(find.text('5.0 / 2.0'), findsOneWidget);
      expect(find.text('3.5'), findsNothing);
      expect(find.text('의견 갈림'), findsOneWidget);
      expect(find.text('조정'), findsOneWidget);
    });

    testWidgets('1점 차는 갈린 것이 아니다', (tester) async {
      await tester.pumpWidget(
        host(
          () async => data([
            entryFor(
              4,
              evaluations: [
                ev(id: 1, evaluatorId: meId, score: 5),
                ev(id: 2, evaluatorId: 2, score: 4),
              ],
              avgScore: 4.5,
            ),
          ]),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('4.5'), findsOneWidget);
      expect(find.text('의견 갈림'), findsNothing);
      expect(find.text('보기'), findsOneWidget);
    });

    testWidgets('내가 안 낸 채 3일을 넘기면 [n일 경과]', (tester) async {
      await tester.pumpWidget(
        host(() async => data([entryFor(4, assignedDaysAgo: 5)])),
      );
      await tester.pumpAndSettle();

      expect(find.text('5일 경과'), findsOneWidget);
    });

    testWidgets('3일째까지는 경과 배지가 없다', (tester) async {
      await tester.pumpWidget(
        host(() async => data([entryFor(4, assignedDaysAgo: 3)])),
      );
      await tester.pumpAndSettle();

      expect(find.text('3일 경과'), findsNothing);
    });

    testWidgets('내가 이미 냈으면 오래돼도 경과 배지가 없다', (tester) async {
      await tester.pumpWidget(
        host(
          () async => data([
            entryFor(
              4,
              assignedDaysAgo: 20,
              evaluations: [ev(id: 1, evaluatorId: meId, score: 4)],
              avgScore: 4,
            ),
          ]),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('20일 경과'), findsNothing);
    });
  });

  group('평가자 아바타', () {
    testWidgets('이름 앞 두 글자를 쓴다 — 서버가 준 이름표로 id 를 바꾼다', (tester) async {
      await tester.pumpWidget(
        host(
          () async => data(
            [
              entryFor(
                4,
                evaluations: [ev(id: 1, evaluatorId: 3, score: 4)],
                avgScore: 4,
              ),
            ],
            names: const {3: '이서연'},
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('이서'), findsOneWidget);
    });

    testWidgets('셋을 넘으면 셋까지만 그리고 나머지는 수로', (tester) async {
      await tester.pumpWidget(
        host(
          () async => data(
            [
              entryFor(
                4,
                evaluations: [
                  ev(id: 1, evaluatorId: 2, score: 4),
                  ev(id: 2, evaluatorId: 3, score: 4),
                  ev(id: 3, evaluatorId: 4, score: 4),
                  ev(id: 4, evaluatorId: 5, score: 4),
                  ev(id: 5, evaluatorId: 6, score: 4),
                ],
                avgScore: 4,
              ),
            ],
            names: const {2: '김채용', 3: '이서연', 4: '박정호', 5: '최민지', 6: '한도윤'},
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('김채'), findsOneWidget);
      expect(find.text('이서'), findsOneWidget);
      expect(find.text('박정'), findsOneWidget);
      expect(find.text('최민'), findsNothing);
      expect(find.text('+2'), findsOneWidget);
    });

    testWidgets('이름을 못 받으면 물음표 — 목록 자체는 막지 않는다', (tester) async {
      await tester.pumpWidget(
        host(
          () async => data([
            entryFor(
              4,
              evaluations: [ev(id: 1, evaluatorId: 9, score: 4)],
              avgScore: 4,
            ),
          ]),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('정우진'), findsOneWidget);
      expect(find.text('?'), findsOneWidget);
    });
  });

  group('공고 레일', () {
    Future<void> pumpTwoPostings(WidgetTester tester) => tester.pumpWidget(
      host(
        () async =>
            data([entryOn(4, 1, '백엔드 개발자 (신입)'), entryOn(1, 3, '데이터 엔지니어')]),
      ),
    );

    testWidgets('공고가 둘이면 전체 + 공고들이 뜬다', (tester) async {
      await pumpTwoPostings(tester);
      await tester.pumpAndSettle();

      expect(find.text('전체'), findsOneWidget);
      expect(find.text('백엔드 개발자 (신입)'), findsOneWidget);
      expect(find.text('데이터 엔지니어'), findsOneWidget);
      // 진행률 — 둘 다 안 냈다
      expect(find.text('0/2'), findsOneWidget);
    });

    testWidgets('공고를 고르면 그 공고만 남는다', (tester) async {
      await pumpTwoPostings(tester);
      await tester.pumpAndSettle();
      expect(find.text('정우진'), findsOneWidget);
      expect(find.text('김도현'), findsOneWidget);

      await tester.tap(find.text('데이터 엔지니어'));
      await tester.pumpAndSettle();

      expect(find.text('정우진'), findsNothing);
      expect(find.text('김도현'), findsOneWidget);
    });

    testWidgets('공고가 하나뿐이면 레일을 접는다 — 전체와 같은 것이다', (tester) async {
      await tester.pumpWidget(
        host(() async => data([entryFor(4), entryFor(1)])),
      );
      await tester.pumpAndSettle();

      expect(find.text('전체'), findsNothing);
    });

    testWidgets('공고명을 못 받으면 레일을 접는다 — 이름 없는 칸은 못 고른다', (tester) async {
      await tester.pumpWidget(
        host(() async => data([entryOn(4, 1, ''), entryOn(1, 3, '')])),
      );
      await tester.pumpAndSettle();

      expect(find.text('전체'), findsNothing);
      expect(find.text('정우진'), findsOneWidget);
    });
  });

  // 목 로더는 큐 8 4단계(2026-09-03)에서 사라졌다 — 큐가 서버에서 온다.
  // 무엇이 큐에 들어가는지는 **서버가 정한다**(내게 배정된 것), 그래서 앱이
  // 검사할 규칙이 없어졌다. 화면 규칙(세 상태·정렬·이동)만 위에서 본다.
}
