/// 표기 규칙 — 05-design §2 "표기 통일".
///
/// 날짜 `2026.09.02` · D-day `D-12` · 건수 `48명`.
/// 화면마다 다르게 쓰지 않도록 여기 한 곳에 둔다.
library;

String _two(int n) => n.toString().padLeft(2, '0');

/// `2026.03.12`
String formatDate(DateTime d) => '${d.year}.${_two(d.month)}.${_two(d.day)}';

/// `48명`
String formatCount(int n) => '$n명';

/// `2026.08.27 14:20` — 단계 이력처럼 시각까지 필요한 곳.
String formatDateTime(DateTime d) =>
    '${formatDate(d)} ${_two(d.hour)}:${_two(d.minute)}';

/// `14:00` — 면접 시각처럼 그날 안의 시각만 필요한 곳.
String formatTime(DateTime d) => '${_two(d.hour)}:${_two(d.minute)}';

/// `2건` — 면접·일정처럼 사람이 아닌 것을 셀 때. 사람은 [formatCount].
String formatItemCount(int n) => '$n건';

/// 주격 조사 — 받침이 있으면 `이`, 없으면 `가`.
///
/// "인적성 검사이 없습니다" 같은 문장을 막는다. 문구에 낱말을 끼워 넣는 자리가
/// 늘면서 필요해졌다(2026-09-08 지원자 화면).
///
/// 한글 음절은 `0xAC00` 부터 28개씩 묶여 있고 그 안의 위치가 종성이다 —
/// 0이면 받침이 없다. 한글이 아니면(영문·숫자) `가` 로 둔다: "AI" 처럼 읽는
/// 소리가 제각각이라 규칙으로 정할 수 없고, 둘 중 하나면 `가` 가 덜 어색하다.
String subjectParticle(String word) {
  if (word.isEmpty) return '가';
  final code = word.codeUnitAt(word.length - 1);
  if (code < 0xAC00 || code > 0xD7A3) return '가';
  return (code - 0xAC00) % 28 == 0 ? '가' : '이';
}

/// `09.01` — 주간 스트립의 기간 표기처럼 연도가 문맥에 이미 있는 곳.
/// 연도까지 필요한 곳은 [formatDate] 를 쓴다(§2 표기 통일).
String formatMonthDay(DateTime d) => '${_two(d.month)}.${_two(d.day)}';
