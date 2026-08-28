/// 전형 단계 — 01-erd.md "단계(stage) 고정 enum" 을 그대로 옮긴 것.
///
/// `applied` → `screening` → `interview` → `accepted` / `rejected`
///
/// **문자열 값은 DB 에 저장되는 값이다.** 한글 라벨은 화면 표시용이며
/// 값과 라벨을 섞어 쓰지 않는다.
library;

enum Stage {
  applied('applied', '지원 접수'),
  screening('screening', '서류 검토'),
  interview('interview', '면접'),
  accepted('accepted', '최종 합격'),
  rejected('rejected', '불합격');

  const Stage(this.value, this.label);

  /// DB 에 저장되는 값 (`applications.current_stage`)
  final String value;

  /// 화면에 보이는 한글 이름
  final String label;

  /// 05-design §1: **색은 판단에만.**
  /// 진행 중(접수·서류·면접)은 무채, 합격만 연두, 불합격만 적갈.
  /// 판단 전 항목에 색을 주지 않는다.
  bool get isDecided => this == accepted || this == rejected;

  static Stage fromValue(String value) =>
      Stage.values.firstWhere((s) => s.value == value);
}

/// 단계 전환 규칙 — `backend/app/stages.py` 를 그대로 옮긴 것.
///
/// 시안(2026-08-28) 1번: **갈 수 있는 단계만 보여 준다.**
/// 갈 수 없는 단계를 눌러 서버에서 409 를 받는 일이 없어야 한다.
///
/// 서버가 여전히 최종 판정자다. 여기 규칙은 화면을 미리 거르기 위한 사본이고,
/// 어긋나면 서버가 기준이다 — 규칙이 바뀌면 stages.py 를 보고 함께 고친다.
extension StageTransitions on Stage {
  /// 전진 경로. `rejected` 는 순서 밖이라 여기 없다.
  static const _order = [
    Stage.applied,
    Stage.screening,
    Stage.interview,
    Stage.accepted,
  ];

  /// 지원자에게 안내 메일이 나가는 단계 — `NOTIFY_STAGES`.
  ///
  /// `screening` 은 내부 검토라 보낼 문구가 없고, `applied` 는 접수 확인 메일(C4)이
  /// 따로 있다. 시안: **메일 경고는 나가는 단계에만** 띄운다.
  /// 늘 띄우면 경고를 안 읽게 된다.
  static const notifyStages = {Stage.interview, Stage.accepted, Stage.rejected};

  bool get notifiesApplicant => notifyStages.contains(this);

  /// 이 단계에서 옮겨 갈 수 있는 단계들.
  List<Stage> get allowedNext => [
    for (final to in Stage.values)
      if (to != this && _canMoveTo(to)) to,
  ];

  bool _canMoveTo(Stage to) {
    // 불합격은 어느 단계에서든 가능
    if (to == Stage.rejected) return true;
    // 불합격에서 되돌리는 것은 뒤로 이동 — 담당자 권한으로 허용
    if (this == Stage.rejected) return true;

    final here = _order.indexOf(this);
    final there = _order.indexOf(to);

    // 뒤로 이동은 허용 (담당자가 되돌리는 경우)
    if (there < here) return true;

    // 전진은 한 칸씩만
    return there - here == 1;
  }

  /// 선택지에 붙는 한 줄 설명 — 시안 1번의 부제.
  String describeMoveTo(Stage to) {
    final direction = switch (to) {
      Stage.rejected => '사유 필요',
      _ when _order.indexOf(to) < _order.indexOf(this) => '되돌리기',
      _ => '다음 단계',
    };
    final mail = to.notifiesApplicant ? '안내 메일 발송' : '메일 없음';
    return '$direction · $mail';
  }
}
