/// 캘린더 (캘린더 탭) — 앱 UI 초안(2026-09-01) 조각 10.
///
/// **월 그리드를 그리지 않는다.** 05-design 캘린더 절이 못 박았다:
///
/// > ≤768px 은 월 그리드가 안 들어가므로 **주간 스트립(선택한 날이 든 한 주 7칸,
/// > 건수만) + 그날 목록**으로 떨어뜨린다(모바일 칸반 금지와 같은 근거 —
/// > 가로 스크롤로 밀어 넣지 않는다).
///
/// 그래서 이동 단위도 달이 아니라 주다. 데이터는 **확정된 일정 제안만**이고
/// (ADR-0016) 이 화면에서 등록·수정·삭제는 없다 — `GET /schedules` 조회 전용.
///
/// "내 면접만"은 권한이 아니라 필터다 — 조회는 로그인한 사람이면 전원 가능하고
/// 역할로 목록을 자르던 A3 는 폐지됐다(05-design 캘린더 절).
library;

import 'package:flutter/material.dart';

import '../data/mock_data.dart';
import '../models/interview.dart';
import '../routes.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';

/// 테스트가 스트립과 날짜 칸을 정확히 집을 손잡이.
/// 날짜 숫자는 건수 숫자와 겹쳐서(2일 vs 2건) 글자만으로는 특정할 수 없다.
const weekStripKey = Key('calendar-week-strip');
Key dayCellKey(DateTime d) => Key('calendar-day-${d.year}-${d.month}-${d.day}');

class CalendarScreen extends StatefulWidget {
  const CalendarScreen({super.key, this.today});

  /// 테스트가 날짜를 고정할 수 있게 열어 둔다. 비면 기기 오늘.
  final DateTime? today;

  @override
  State<CalendarScreen> createState() => _CalendarScreenState();
}

class _CalendarScreenState extends State<CalendarScreen> {
  late final DateTime _today = _dateOnly(widget.today ?? DateTime.now());
  late DateTime _selected = _today;

  /// 05-design: 자기가 면접관인 건만 좁히는 **필터**. 기본은 전체.
  bool _mineOnly = false;

  static DateTime _dateOnly(DateTime d) => DateTime(d.year, d.month, d.day);

  /// 목데이터에는 배정이 없어 면접관 이름으로 대신한다 — API 연동 때 내 user id 로 바뀐다
  static const _me = mockMyName;

  List<Interview> _filter(List<Interview> items) =>
      _mineOnly ? items.where((i) => i.interviewerName == _me).toList() : items;

  void _moveWeek(int weeks) {
    setState(() {
      _selected = _selected.add(Duration(days: 7 * weeks));
    });
  }

  @override
  Widget build(BuildContext context) {
    final week = mockInterviewsInWeek(_selected);
    final days = week.keys.toList()..sort();
    final selectedItems = _filter(week[_selected] ?? const []);

    return ListView(
      padding: const EdgeInsets.all(AppSpace.s4),
      children: [
        _Controls(
          rangeLabel:
              '${formatMonthDay(days.first)} – ${formatMonthDay(days.last)}',
          mineOnly: _mineOnly,
          onPrev: () => _moveWeek(-1),
          onNext: () => _moveWeek(1),
          onToggleMine: () => setState(() => _mineOnly = !_mineOnly),
          onToday: () => setState(() => _selected = _today),
        ),
        const SizedBox(height: AppSpace.s3),
        _WeekStrip(
          days: days,
          selected: _selected,
          today: _today,
          countOf: (day) => _filter(week[day] ?? const []).length,
          onSelect: (day) => setState(() => _selected = day),
        ),
        const SizedBox(height: AppSpace.s5),
        _DayHeader(day: _selected, count: selectedItems.length),
        const SizedBox(height: AppSpace.s2),
        if (selectedItems.isEmpty)
          const _EmptyDay()
        else
          _DayList(items: selectedItems),
      ],
    );
  }
}

/// 주 이동 · 내 면접만 · 오늘.
///
/// 05-design 은 웹 캘린더에 "이전/다음 **달**" 을 두지만, 앱은 스트립이 한 주라
/// 이동도 주 단위다. 달을 옮기는 컨트롤을 두면 화면에 없는 날로 가 버린다.
class _Controls extends StatelessWidget {
  const _Controls({
    required this.rangeLabel,
    required this.mineOnly,
    required this.onPrev,
    required this.onNext,
    required this.onToggleMine,
    required this.onToday,
  });

  final String rangeLabel;
  final bool mineOnly;
  final VoidCallback onPrev;
  final VoidCallback onNext;
  final VoidCallback onToggleMine;
  final VoidCallback onToday;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        _RoundIcon(icon: Icons.chevron_left, label: '지난 주', onTap: onPrev),
        Text(
          rangeLabel,
          softWrap: false,
          style: const TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.h2,
            fontWeight: FontWeight.w700,
            fontFeatures: AppType.tabularNums,
            color: AppColors.text,
            shadows: AppTextShadow.heading,
          ),
        ),
        _RoundIcon(icon: Icons.chevron_right, label: '다음 주', onTap: onNext),
        const Spacer(),
        _Pill(label: '내 면접만', selected: mineOnly, onTap: onToggleMine),
        const SizedBox(width: AppSpace.s2),
        _Pill(label: '오늘', selected: false, onTap: onToday),
      ],
    );
  }
}

class _RoundIcon extends StatelessWidget {
  const _RoundIcon({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: label,
      child: Material(
        color: Colors.transparent,
        shape: const CircleBorder(),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          highlightColor: AppColors.bgSunken,
          splashColor: AppColors.bgSunken,
          // §9 터치 타깃 44
          child: SizedBox(
            width: AppLayout.minTouchTarget,
            height: AppLayout.minTouchTarget,
            child: Icon(icon, size: 24, color: AppColors.textSub),
          ),
        ),
      ),
    );
  }
}

/// 알약 버튼 — 켜지면 연두 워시 + 잎 글자(05-design §1).
class _Pill extends StatelessWidget {
  const _Pill({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: selected,
      child: Material(
        color: selected ? AppColors.sproutSoft : AppColors.bgSunken,
        borderRadius: AppShape.pill,
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          highlightColor: AppColors.sunkenHover,
          splashColor: AppColors.sunkenHover,
          child: Container(
            height: 32,
            padding: const EdgeInsets.symmetric(horizontal: AppSpace.s3),
            alignment: Alignment.center,
            decoration: BoxDecoration(
              borderRadius: AppShape.pill,
              border: Border.all(
                color: selected ? AppColors.sprout : AppColors.border,
                width: AppShape.borderW,
              ),
            ),
            child: Text(
              label,
              softWrap: false,
              style: TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.sm,
                fontWeight: selected ? AppType.wSemiBold : AppType.wRegular,
                color: selected ? AppColors.leaf : AppColors.textSub,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// 주간 스트립 — 한 주 7칸, **건수만**.
///
/// 월 그리드가 셀에 면접 3건까지 적고 넘치면 `+N건` 으로 접는 것과 달리,
/// 스트립은 숫자 하나만 놓는다. 45dp 칸에 이름이 들어가지 않는다.
class _WeekStrip extends StatelessWidget {
  const _WeekStrip({
    required this.days,
    required this.selected,
    required this.today,
    required this.countOf,
    required this.onSelect,
  });

  final List<DateTime> days;
  final DateTime selected;
  final DateTime today;
  final int Function(DateTime) countOf;
  final ValueChanged<DateTime> onSelect;

  static const _labels = ['일', '월', '화', '수', '목', '금', '토'];

  @override
  Widget build(BuildContext context) {
    return Container(
      key: weekStripKey,
      padding: const EdgeInsets.all(AppSpace.s2),
      decoration: BoxDecoration(
        color: AppColors.bgElev,
        borderRadius: AppShape.card,
        border: Border.all(color: AppColors.border, width: AppShape.borderW),
        boxShadow: AppShadow.card,
      ),
      child: Row(
        children: [
          for (var i = 0; i < days.length; i++)
            Expanded(
              child: _DayCell(
                key: dayCellKey(days[i]),
                day: days[i],
                weekdayLabel: _labels[i],
                count: countOf(days[i]),
                isSelected: days[i] == selected,
                isToday: days[i] == today,
                isSunday: i == 0,
                onTap: () => onSelect(days[i]),
              ),
            ),
        ],
      ),
    );
  }
}

class _DayCell extends StatelessWidget {
  const _DayCell({
    super.key,
    required this.day,
    required this.weekdayLabel,
    required this.count,
    required this.isSelected,
    required this.isToday,
    required this.isSunday,
    required this.onTap,
  });

  final DateTime day;
  final String weekdayLabel;
  final int count;
  final bool isSelected;
  final bool isToday;
  final bool isSunday;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    // 일요일만 적갈 — 05-design §1 은 danger 를 "종료 신호"로 쓰지만 달력의
    // 일요일 빨강은 사람들이 읽는 관습이라 같은 토큰을 빌려 쓴다. 새 색은 만들지 않는다
    final baseColor = isSunday ? AppColors.danger : AppColors.text;

    return Semantics(
      button: true,
      selected: isSelected,
      label: '${formatDate(day)} 면접 $count건',
      excludeSemantics: true,
      child: Material(
        color: isSelected
            ? AppColors.leaf
            : isToday
            ? AppColors.bgSunken
            : Colors.transparent,
        borderRadius: AppShape.ctl,
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          highlightColor: AppColors.bgSunken,
          splashColor: AppColors.bgSunken,
          child: SizedBox(
            // §9 터치 타깃 44
            // 요일·날짜·건수 세 줄 + §9 터치 타깃 44. 44+12 로는 6px 넘친다
            height: AppLayout.minTouchTarget + AppSpace.s5,
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  weekdayLabel,
                  style: TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.caption,
                    color: isSelected ? AppColors.bgElev : AppColors.textSub,
                  ),
                ),
                const SizedBox(height: AppSpace.s1),
                Text(
                  '${day.day}',
                  style: TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.num,
                    fontWeight: isSelected || isToday
                        ? AppType.wSemiBold
                        : AppType.wRegular,
                    fontFeatures: AppType.tabularNums,
                    color: isSelected ? AppColors.bgElev : baseColor,
                  ),
                ),
                const SizedBox(height: AppSpace.s1),
                Text(
                  '$count',
                  style: TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.caption,
                    fontWeight: AppType.wSemiBold,
                    fontFeatures: AppType.tabularNums,
                    // 0건은 테두리색까지 흐려 둔다 — 있는 날과 없는 날이 한눈에 갈려야 한다
                    color: isSelected
                        ? AppColors.bgElev
                        : count == 0
                        ? AppColors.border
                        : AppColors.leaf,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _DayHeader extends StatelessWidget {
  const _DayHeader({required this.day, required this.count});

  final DateTime day;
  final int count;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Text(
          formatDate(day),
          style: const TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.sm,
            fontWeight: AppType.wSemiBold,
            fontFeatures: AppType.tabularNums,
            color: AppColors.text,
          ),
        ),
        const Spacer(),
        Text(
          formatItemCount(count),
          style: const TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.sm,
            fontFeatures: AppType.tabularNums,
            color: AppColors.textSub,
          ),
        ),
      ],
    );
  }
}

/// 그날 목록 — 시각 · 지원자 · 공고 · 면접관.
///
/// 05-design 은 이 목록을 테이블로 두지만 §9 가 "테이블은 카드형"이라 카드 행으로 편다.
/// 같은 시각이 여러 건이면 시각은 첫 행에만 적는다 — "같은 시간대는 슬롯으로 묶고
/// 대표는 그 슬롯에서 가장 이른 면접"(캘린더 절)의 앱 표기다.
class _DayList extends StatelessWidget {
  const _DayList({required this.items});

  final List<Interview> items;

  @override
  Widget build(BuildContext context) {
    final sorted = [...items]..sort((a, b) => a.startAt.compareTo(b.startAt));

    return Container(
      decoration: BoxDecoration(
        color: AppColors.bgElev,
        borderRadius: AppShape.card,
        border: Border.all(color: AppColors.border, width: AppShape.borderW),
        boxShadow: AppShadow.card,
      ),
      child: Column(
        children: [
          for (var i = 0; i < sorted.length; i++)
            _Row(
              interview: sorted[i],
              // 앞 건과 같은 시각이면 시각을 다시 적지 않는다
              showTime: i == 0 || sorted[i].startAt != sorted[i - 1].startAt,
              first: i == 0,
            ),
        ],
      ),
    );
  }
}

class _Row extends StatelessWidget {
  const _Row({
    required this.interview,
    required this.showTime,
    required this.first,
  });

  final Interview interview;
  final bool showTime;
  final bool first;

  /// 05-design 캘린더 절(2026-09-01): "**행 클릭 = 그 지원자의 상세 패널**".
  ///
  /// 웹은 `/postings/{공고}?applicant={지원}` 으로 보내 공고의 지원자 화면이 그
  /// 사람을 연 채로 뜨게 한다. 앱은 상세가 별도 화면이라 곧장 그리로 간다.
  ///
  /// API 주의(큐 8): `GET /schedules` 는 **공고 id 를 주지 않는다** — 웹은 상세를
  /// 한 번 더 받아 알아낸다. 여기서는 목데이터라 지원자 id 로 바로 찾는다.
  void _openDetail(BuildContext context) {
    final applicant = mockApplicants
        .where((a) => a.id == interview.applicationId)
        .firstOrNull;
    if (applicant == null) return;

    Navigator.pushNamed(
      context,
      Routes.applicantDetail,
      arguments: (applicant, interview.postingTitle),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        border: first
            ? null
            : const Border(
                top: BorderSide(
                  color: AppColors.borderSoft,
                  width: AppShape.borderW,
                ),
              ),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: () => _openDetail(context),
          // §5: 모바일은 hover 없음 전제 — press 만 정의한다
          highlightColor: AppColors.bgSunken,
          splashColor: AppColors.bgSunken,
          child: Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpace.s4,
              vertical: AppSpace.s3,
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(
                  width: 48,
                  child: Text(
                    showTime ? formatTime(interview.startAt) : '',
                    softWrap: false,
                    style: const TextStyle(
                      fontFamily: AppType.fontFamily,
                      fontSize: AppType.num,
                      fontWeight: AppType.wSemiBold,
                      fontFeatures: AppType.tabularNums,
                      color: AppColors.leaf,
                    ),
                  ),
                ),
                const SizedBox(width: AppSpace.s3),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        interview.applicantName,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontFamily: AppType.fontFamily,
                          fontSize: AppType.body,
                          fontWeight: AppType.wSemiBold,
                          color: AppColors.text,
                        ),
                      ),
                      const SizedBox(height: AppSpace.s1),
                      Text(
                        interview.postingTitle,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontFamily: AppType.fontFamily,
                          fontSize: AppType.caption,
                          color: AppColors.textSub,
                        ),
                      ),
                      const SizedBox(height: AppSpace.s1),
                      Text(
                        '면접관 ${interview.interviewerName}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontFamily: AppType.fontFamily,
                          fontSize: AppType.caption,
                          color: AppColors.textSub,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// 면접이 없는 날. 05-design §6 의 빈 상태 — 웹 대시보드가 쓰는 문구를 그대로 쓴다.
class _EmptyDay extends StatelessWidget {
  const _EmptyDay();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: AppSpace.s7),
      decoration: BoxDecoration(
        color: AppColors.bgElev,
        borderRadius: AppShape.card,
        border: Border.all(color: AppColors.border, width: AppShape.borderW),
        boxShadow: AppShadow.card,
      ),
      child: const Text(
        '면접 없음',
        textAlign: TextAlign.center,
        style: TextStyle(
          fontFamily: AppType.fontFamily,
          fontSize: AppType.sm,
          color: AppColors.textSub,
        ),
      ),
    );
  }
}
