// 단계 전환 규칙 — backend/app/stages.py 의 사본이다.
// 어긋나면 화면이 갈 수 없는 단계를 보여 주고 서버에서 409 를 받는다.

import 'package:arda/models/stage.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('갈 수 있는 단계', () {
    test('지원 접수 → 서류 검토(한 칸) · 불합격만', () {
      expect(Stage.applied.allowedNext, [Stage.screening, Stage.rejected]);
    });

    test('전진은 한 칸씩 — 지원 접수에서 면접으로 못 간다', () {
      expect(Stage.applied.allowedNext, isNot(contains(Stage.interview)));
    });

    test('되돌리기는 몇 칸이든 허용 — 면접에서 지원 접수로', () {
      expect(
        Stage.interview.allowedNext,
        containsAll([Stage.applied, Stage.screening]),
      );
    });

    test('불합격은 어느 단계에서든 가능', () {
      for (final s in Stage.values) {
        if (s == Stage.rejected) continue;
        expect(s.allowedNext, contains(Stage.rejected), reason: '$s 에서');
      }
    });

    test('불합격에서는 어디로든 되돌릴 수 있다', () {
      expect(Stage.rejected.allowedNext.length, 4);
    });

    test('자기 자신은 선택지에 없다', () {
      for (final s in Stage.values) {
        expect(s.allowedNext, isNot(contains(s)), reason: '$s');
      }
    });
  });

  group('메일 발송 단계 — NOTIFY_STAGES', () {
    test('면접·최종 합격·불합격만 메일이 나간다', () {
      expect(Stage.interview.notifiesApplicant, isTrue);
      expect(Stage.accepted.notifiesApplicant, isTrue);
      expect(Stage.rejected.notifiesApplicant, isTrue);
    });

    test('지원 접수·서류 검토는 메일이 없다', () {
      // screening 은 내부 검토라 보낼 문구가 없고, applied 는 C4 확인 메일이 따로 있다
      expect(Stage.applied.notifiesApplicant, isFalse);
      expect(Stage.screening.notifiesApplicant, isFalse);
    });
  });

  group('선택지 설명', () {
    test('다음 단계 + 메일', () {
      expect(
        Stage.screening.describeMoveTo(Stage.interview),
        '다음 단계 · 안내 메일 발송',
      );
    });

    test('되돌리기 + 메일 없음', () {
      expect(
        Stage.screening.describeMoveTo(Stage.applied),
        '되돌리기 · 메일 없음',
      );
    });

    test('불합격은 사유 필요', () {
      expect(
        Stage.screening.describeMoveTo(Stage.rejected),
        '사유 필요 · 안내 메일 발송',
      );
    });
  });
}
