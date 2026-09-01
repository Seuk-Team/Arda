/// 단계 변경 이력 — 01-erd.md `stage_history` 테이블.
///
/// 시안(2026-08-28) 2번: 어느 목업에도 없던 화면이다. 서버가 이전 단계·다음 단계·
/// 바꾼 사람·시각·사유를 남기고 있어 그대로 시간순으로 편다.
library;

import 'stage.dart';

class StageHistory {
  const StageHistory({
    required this.id,
    required this.applicationId,
    this.fromStage,
    required this.toStage,
    this.changedByName,
    this.reason,
    required this.mailQueued,
    required this.createdAt,
  });

  /// `stage_history.id`
  final int id;

  /// `stage_history.application_id`
  final int applicationId;

  /// `stage_history.from_stage` — **최초 접수 시 NULL** (ERD)
  final Stage? fromStage;

  /// `stage_history.to_stage`
  final Stage toStage;

  /// `stage_history.changed_by` → 사람 이름.
  /// **NULL = 시스템(외부 지원 접수)** — ERD 비고
  final String? changedByName;

  /// `stage_history.reason` — 불합격 사유 (D8). `rejected` 진입 시 기록
  final String? reason;

  /// 이 변경으로 지원자에게 메일이 나갔는지 (02-api 응답의 `mail_queued`).
  /// 시안: "메일이 갔나?"는 단계 이력을 여는 가장 흔한 이유다
  final bool mailQueued;

  /// `stage_history.created_at`
  final DateTime createdAt;

  /// 시안: 단계 이름만 나열하면 되돌린 건지 전진한 건지 구분되지 않는다.
  /// `from_stage` 를 주로 붙여 "면접에서 → 최종 합격"이 한 줄에 읽히게 한다.
  String? get fromLabel => fromStage == null ? null : '${fromStage!.label}에서';

  /// 누가 바꿨는지. 시스템이면 지원자가 직접 낸 것이다
  String get actorLabel => changedByName ?? '지원자 제출';
}
