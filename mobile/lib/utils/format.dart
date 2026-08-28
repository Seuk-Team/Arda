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
