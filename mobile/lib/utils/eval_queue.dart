/// 평가 현황 목록의 계산 — 공고 레일 + 상태가 보이는 줄.
///
/// 웹(`frontend/app/src/lib/evalQueue.ts`)을 그대로 옮긴 것이다. 규칙이 두
/// 곳에 따로 살면 "웹에선 갈렸다는데 폰에선 아니다" 같은 일이 생긴다 —
/// 임계값(`splitGap`·`staleDays`)과 점수 표기를 웹과 같은 값으로 둔다.
///
/// 부르는 API 는 전부 이미 열려 있다(백엔드 변경 없음):
///   GET /interviewers/{me}/applications → 배정 + 배정일
///   GET /applications/{id}             → evaluations[] · avg_score
///   GET /users                         → evaluator_id → 이름
///   GET /postings                      → 공고 이름
///
/// 화면(그리기)은 `screens/evaluation_queue_screen.dart` 가 한다.
library;

import '../models/applicant.dart';
import '../models/evaluation.dart';

/// 최고−최저가 이만큼 벌어지면 '의견 갈림'. 1~5 척도에서 2 는 "좋다"와
/// "보통"이 아니라 "뽑자"와 "아니다" 만큼의 거리다
const splitGap = 2;

/// 배정 후 이 일수를 넘겼는데 내가 아직 안 냈으면 경과 표시
const staleDays = 3;

/// 평가 대기 한 줄에 필요한 것 전부.
///
/// 배정 응답에는 이름도 공고명도 없어서(`AssignmentOut` 은 id 뿐) 화면을
/// 그리려면 건마다 상세를 한 번 더 받아야 한다 — 그 결과를 여기 모아 둔다.
class QueueEntry {
  const QueueEntry({
    required this.applicant,
    required this.postingTitle,
    required this.assignedAt,
    this.evaluations = const [],
    this.avgScore,
  });

  final Applicant applicant;

  /// 못 받으면 빈 문자열이다 — 공고명을 몰라도 큐는 보여 준다(웹과 같은 처리)
  final String postingTitle;

  /// 배정 시각 — `assignments[].created_at`. '배정 n일째' 의 기준이다
  final DateTime assignedAt;

  /// 이 지원자에게 달린 평가 전부(내 것 포함)
  final List<Evaluation> evaluations;

  /// 서버가 계산한 평균. 평가가 없으면 null — **0.0 이 아니다**
  final double? avgScore;

  int get postingId => applicant.jobPostingId;
}

/// 화면이 한 번에 받는 것 — 줄들 + 이름표 + 내가 누구인지.
///
/// [evaluatorNames] 를 따로 들고 다니는 이유: 서버는 평가에 **id 만** 준다
/// (`EvaluationOut`). 이름은 `GET /users` 로 따로 받아 여기서 맞춘다.
/// 못 받으면 아바타가 '?' 로 뜨고, 목록 자체는 막지 않는다.
///
/// [meId] 는 "내가 낸 평가"를 가려내는 데만 쓴다. 모르면(null) 전부 남의
/// 평가로 본다 — 남의 것을 내 것이라고 우기는 쪽이 더 나쁘다.
class QueueData {
  const QueueData({
    required this.entries,
    this.evaluatorNames = const {},
    this.meId,
  });

  final List<QueueEntry> entries;
  final Map<int, String> evaluatorNames;
  final int? meId;

  bool get isEmpty => entries.isEmpty;
}

/// 점수 칸의 색 — 색만으로 뜻을 나르지 않는다(글자가 늘 같이 있다)
enum ScoreTone { ok, warn, none }

/// 한 줄이 화면에 내보이는 것 전부. 계산은 [buildRows] 가 한 번에 한다
class QueueRow {
  const QueueRow({
    required this.entry,
    required this.mine,
    required this.others,
    required this.days,
    required this.split,
    required this.scoreText,
    required this.scoreTone,
    required this.sub,
  });

  final QueueEntry entry;

  /// 내가 낸 평가. 없으면 아직 내 차례다
  final Evaluation? mine;
  final List<Evaluation> others;

  /// 배정 후 지난 날수
  final int days;
  final bool split;

  /// 갈렸으면 "5.0 / 2.0" 처럼 양끝을 보여 준다 — 평균 3.5 하나만 적으면
  /// "무난함" 으로 읽혀 갈린 사실이 지워진다
  final String scoreText;
  final ScoreTone scoreTone;

  /// 점수 아래 작은 줄. 없으면 빈 문자열
  final String sub;

  int get postingId => entry.postingId;
  String get postingTitle => entry.postingTitle;
  Applicant get applicant => entry.applicant;

  /// 내가 안 낸 채로 [staleDays] 를 넘겼다
  bool get stale => mine == null && days > staleDays;

  /// 눌렀을 때 무엇을 하게 되는지. 배지·점수가 이미 상태를 말하고 이건
  /// **다음 동작**을 말한다
  String get action => mine == null
      ? '평가'
      : split
      ? '조정'
      : '보기';

  /// 아바타로 보여 줄 평가 — **내 것이 맨 앞**이다. 이 줄에서 내가 어디 서
  /// 있는지가 먼저다
  List<Evaluation> get evaluators => [?mine, ...others];
}

List<QueueRow> buildRows(QueueData data, {DateTime? now}) {
  final today = now ?? DateTime.now();
  return [for (final entry in data.entries) _row(entry, data.meId, today)];
}

QueueRow _row(QueueEntry entry, int? meId, DateTime now) {
  final evals = entry.evaluations;
  Evaluation? mine;
  if (meId != null) {
    for (final e in evals) {
      if (e.evaluatorId == meId) {
        mine = e;
        break;
      }
    }
  }
  final others = [
    for (final e in evals)
      if (!identical(e, mine)) e,
  ];
  final scores = [for (final e in evals) e.score];

  var split = false;
  var scoreText = '미착수';
  var scoreTone = ScoreTone.none;
  var sub = '';

  if (scores.isNotEmpty) {
    final lo = scores.reduce((a, b) => a < b ? a : b);
    final hi = scores.reduce((a, b) => a > b ? a : b);
    split = scores.length >= 2 && hi - lo >= splitGap;
    if (split) {
      scoreText = '${hi.toStringAsFixed(1)} / ${lo.toStringAsFixed(1)}';
      scoreTone = ScoreTone.warn;
    } else {
      final avg =
          entry.avgScore ?? scores.reduce((a, b) => a + b) / scores.length;
      scoreText = avg.toStringAsFixed(1);
      // 남들만 냈으면 아직 내 차례다 — 초록으로 칠하면 끝난 줄로 보인다
      scoreTone = mine == null ? ScoreTone.none : ScoreTone.ok;
      if (mine == null) sub = '${others.length}명 제출';
    }
  }

  return QueueRow(
    entry: entry,
    mine: mine,
    others: others,
    days: _daysSince(entry.assignedAt, now),
    split: split,
    scoreText: scoreText,
    scoreTone: scoreTone,
    sub: sub,
  );
}

/// 날짜만 본다 — 시각까지 세면 오전에 배정된 건과 오후에 배정된 건이 같은
/// 날인데 다른 날수로 나온다
int _daysSince(DateTime from, DateTime now) {
  final a = DateTime(from.year, from.month, from.day);
  final b = DateTime(now.year, now.month, now.day);
  final days = b.difference(a).inDays;
  return days < 0 ? 0 : days;
}

/// 공고 레일 한 칸 — 고르는 곳이면서 진행률 표시다
class QueueGroup {
  const QueueGroup({
    required this.id,
    required this.title,
    required this.done,
    required this.total,
  });

  /// 공고 id. `null` 이면 '전체'
  final int? id;
  final String title;

  /// 내가 평가를 낸 건수
  final int done;
  final int total;

  double get ratio => total == 0 ? 0 : done / total;
}

/// '전체' 가 맨 앞에 있어 공고를 가로지르는 시야를 잃지 않는다.
///
/// 공고가 하나뿐이면 '전체' 와 그 공고가 같은 것이라 화면이 레일을 접는다
/// (그건 화면 쪽 판단이다 — 여기서는 늘 다 만든다).
List<QueueGroup> buildGroups(List<QueueRow> rows) {
  final byPosting = <int, List<QueueRow>>{};
  for (final r in rows) {
    (byPosting[r.postingId] ??= []).add(r);
  }
  int done(List<QueueRow> list) => list.where((r) => r.mine != null).length;

  return [
    QueueGroup(id: null, title: '전체', done: done(rows), total: rows.length),
    for (final e in byPosting.entries)
      QueueGroup(
        id: e.key,
        title: e.value.first.postingTitle,
        done: done(e.value),
        total: e.value.length,
      ),
  ];
}

/// 아바타 한 개의 모양.
class Avatar {
  const Avatar({required this.initials, required this.bg, required this.fg});

  final String initials;
  final int bg;
  final int fg;
}

/// 같은 성씨가 흔해 이니셜만으로는 구분이 안 된다 — 이름을 해시해 색을
/// 고정한다. 같은 사람은 어느 화면에서든 같은 색이다(웹과 같은 팔레트·같은 해시)
const _palette = <(int, int)>[
  (0x3322D3EE, 0xFF7DD3FC),
  (0x33A78BFA, 0xFFC4B5FD),
  (0x3334D399, 0xFF6EE7B7),
  (0x2EFBBF24, 0xFFFCD34D),
  (0x3360A5FA, 0xFF93C5FD),
  (0x2EF0A38F, 0xFFF0A38F),
];

Avatar avatarOf(String name) {
  var h = 0;
  for (final unit in name.codeUnits) {
    h = (h * 31 + unit) & 0xFFFFFFFF;
  }
  final (bg, fg) = _palette[h % _palette.length];
  // 앞 두 글자 — 한글 이름은 성 + 이름 첫 자가 가장 잘 구분된다
  final initials = name.length <= 2 ? name : name.substring(0, 2);
  return Avatar(initials: initials, bg: bg, fg: fg);
}
