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
