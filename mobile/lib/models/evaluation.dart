/// 평가 — 01-erd.md `evaluations` 테이블.
///
/// 시안(2026-08-28) 3번: 웹에는 있는데 폰에서 놓을 자리가 없던 것이다.
/// 상세 화면 안의 한 섹션이 아니라 **별도 화면**으로 뺐다 —
/// 코멘트가 길어 상세에 끼우면 지원 정보가 아래로 밀린다.
library;

class Evaluation {
  const Evaluation({
    required this.id,
    required this.applicationId,
    this.evaluatorName,
    required this.score,
    this.comment,
    required this.createdAt,
  });

  /// `evaluations.id`
  final int id;

  /// `evaluations.application_id`
  final int applicationId;

  /// `evaluations.evaluator_id` → 사람 이름
  /// **서버는 이름을 주지 않는다** — `EvaluationOut` 은 `evaluator_id` 뿐이다
  /// (2026-09-02 실측). id 를 화면에 띄우는 것은 의미가 없어 null 이면 안 그린다.
  /// 백엔드가 이름을 넣어 주면 그때 다시 보인다.
  final String? evaluatorName;

  /// `evaluations.score` — **1~5 체크 제약** (ERD)
  final int score;

  /// `evaluations.comment`
  final String? comment;

  /// `evaluations.created_at`
  final DateTime createdAt;
}

/// 평가 묶음 — D1·E2 응답의 `avg_score` · `count` · 목록에 대응한다.
class EvaluationSummary {
  const EvaluationSummary({required this.items});

  final List<Evaluation> items;

  int get count => items.length;

  /// `avg_score` — 소수 첫째 자리. 평가가 없으면 null (D1 지시서)
  double? get avgScore {
    if (items.isEmpty) return null;
    final sum = items.fold(0, (a, e) => a + e.score);
    return double.parse((sum / items.length).toStringAsFixed(1));
  }

  /// 점수(5→1) → 인원. 시안: **점수 분포를 막대로.**
  /// 평균 4.3이 "4·4·5"인지 "3·5·5"인지는 다른 이야기다.
  Map<int, int> get distribution => {
    for (var s = 5; s >= 1; s--) s: items.where((e) => e.score == s).length,
  };
}

/// 서버 응답 → 모델. `EvaluationOut`.
///
/// **`evaluator_id` 만 온다** — 이름이 없어 [Evaluation.evaluatorName] 은 비운다.
extension EvaluationJson on Evaluation {
  static Evaluation fromJson(
    Map<String, dynamic> json, {
    required int applicationId,
  }) => Evaluation(
    id: json['id'] as int,
    applicationId: applicationId,
    evaluatorName: json['evaluator_name'] as String?,
    score: json['score'] as int,
    comment: json['comment'] as String?,
    createdAt: DateTime.parse(json['created_at'] as String),
  );
}
