/// 지원자 홈 — 전체 메뉴 요약 (2026-09-08).
///
/// 탭 넷이 지금 각각 어떤지 한 화면에 모은다. 지원자가 앱을 켜는 이유는
/// **"내가 지금 뭘 해야 하지"** 하나라, 홈은 그 답만 한다: 할 일이 있는 줄은
/// 채운 버튼으로, 끝났거나 기다리는 줄은 조용히.
///
/// 넷을 **한꺼번에** 받는다. 순서대로 기다리면 홈을 열 때마다 왕복이 넷 쌓인다.
/// 하나가 실패해도 나머지는 보여 준다 — 통째로 실패시키면 멀쩡한 것까지 가린다.
library;

import 'package:flutter/material.dart';

import '../api/api_error.dart';
import '../auth/applicant_store.dart';
import '../data/applicant_demo.dart';
import '../data/applicant_portal_repository.dart';
import '../models/applicant_extra.dart';
import '../models/applicant_portal.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';
import 'applicant_shell.dart';

/// 한 줄이 화면에 내보이는 것. 어느 탭으로 가는지까지 같이 들고 있다
class _Line {
  const _Line({
    required this.tab,
    required this.label,
    required this.state,
    required this.action,
    this.tone = _Tone.quiet,
  });

  final ApplicantTab tab;
  final String label;

  /// 지금 어떤지 — 한 줄
  final String state;

  /// 눌렀을 때 무엇을 하게 되는지. 빈 문자열이면 버튼을 안 그린다
  final String action;

  final _Tone tone;
}

/// 할 일이 있는가. **색은 거들 뿐이고 글자가 늘 같이 있다**
enum _Tone { todo, done, quiet }

class ApplicantSummaryScreen extends StatefulWidget {
  const ApplicantSummaryScreen({
    super.key,
    required this.tokens,
    required this.onOpen,
    this.portal,
  });

  final Map<ApplicantTokenKind, String> tokens;

  /// 탭을 옮겨 준다 — 요약은 자기가 어느 셸에 앉아 있는지 몰라야 한다
  final ValueChanged<ApplicantTab> onOpen;

  /// 테스트가 가짜를 넣는 자리
  final ApplicantPortalRepository? portal;

  @override
  State<ApplicantSummaryScreen> createState() => _ApplicantSummaryScreenState();
}

class _ApplicantSummaryScreenState extends State<ApplicantSummaryScreen> {
  late final ApplicantPortalRepository _portal =
      widget.portal ?? applicantPortal();

  PortalStatus? _status;
  AptitudePublic? _aptitude;
  SchedulePublic? _schedule;
  InterviewPublic? _interview;

  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    // 넷을 한꺼번에. 실패한 것만 null 로 남는다
    await Future.wait([
      _try(
        ApplicantTokenKind.portal,
        (t) async => _status = await _portal.status(t),
      ),
      _try(
        ApplicantTokenKind.aptitude,
        (t) async => _aptitude = await _portal.aptitude(t),
      ),
      _try(
        ApplicantTokenKind.schedule,
        (t) async => _schedule = await _portal.schedule(t),
      ),
      _try(
        ApplicantTokenKind.interview,
        (t) async => _interview = await _portal.interview(t),
      ),
    ]);
    if (!mounted) return;
    setState(() => _loading = false);
  }

  Future<void> _try(
    ApplicantTokenKind kind,
    Future<void> Function(String token) call,
  ) async {
    final token = widget.tokens[kind];
    if (token == null) return;
    try {
      await call(token);
    } on ApiError {
      // 못 받은 것은 "아직 없음" 과 같게 그린다. 지원자가 할 수 있는 일이 같다
    }
  }

  List<_Line> get _lines => [
    _aptitudeLine(),
    _scheduleLine(),
    _interviewLine(),
    _statusLine(),
  ];

  _Line _aptitudeLine() {
    final a = _aptitude;
    return switch (a?.status) {
      null => const _Line(
        tab: ApplicantTab.aptitude,
        label: '인적성 검사',
        state: '아직 없습니다',
        action: '',
      ),
      AptitudeStatus.pending => _Line(
        tab: ApplicantTab.aptitude,
        label: '인적성 검사',
        state: '${a!.questions.length}문항 · 아직 안 냈습니다',
        action: '검사하기',
        tone: _Tone.todo,
      ),
      AptitudeStatus.submitted => const _Line(
        tab: ApplicantTab.aptitude,
        label: '인적성 검사',
        state: '제출했습니다',
        action: '보기',
        tone: _Tone.done,
      ),
      AptitudeStatus.expired => const _Line(
        tab: ApplicantTab.aptitude,
        label: '인적성 검사',
        state: '기한이 지났습니다',
        action: '보기',
      ),
    };
  }

  _Line _scheduleLine() {
    final s = _schedule;
    return switch (s?.status) {
      null => const _Line(
        tab: ApplicantTab.schedule,
        label: '면접 시간',
        state: '아직 없습니다',
        action: '',
      ),
      ScheduleStatus.proposed => _Line(
        tab: ApplicantTab.schedule,
        label: '면접 시간',
        state: '후보 ${formatItemCount(s!.slots.length)} · 골라 주세요',
        action: '시간 고르기',
        tone: _Tone.todo,
      ),
      ScheduleStatus.confirmed => _Line(
        tab: ApplicantTab.schedule,
        label: '면접 시간',
        state: s!.confirmedSlot == null
            ? '확정됐습니다'
            : '${formatDate(s.confirmedSlot!.startAt)} '
                  '${formatTime(s.confirmedSlot!.startAt)} 확정',
        action: '보기',
        tone: _Tone.done,
      ),
      ScheduleStatus.expired => const _Line(
        tab: ApplicantTab.schedule,
        label: '면접 시간',
        state: '선택 기한이 지났습니다',
        action: '보기',
      ),
    };
  }

  _Line _interviewLine() {
    final i = _interview;
    if (i == null) {
      return const _Line(
        tab: ApplicantTab.interview,
        label: 'AI 면접',
        state: '아직 없습니다',
        action: '',
      );
    }
    return switch (i.status) {
      InterviewStatus.pending => _Line(
        tab: ApplicantTab.interview,
        label: 'AI 면접',
        state: i.consentRequired ? '동의 후 시작할 수 있습니다' : '아직 시작하지 않았습니다',
        action: '면접 보기',
        tone: _Tone.todo,
      ),
      InterviewStatus.inProgress => const _Line(
        tab: ApplicantTab.interview,
        label: 'AI 면접',
        state: '진행 중입니다',
        action: '이어서 보기',
        tone: _Tone.todo,
      ),
      InterviewStatus.done => const _Line(
        tab: ApplicantTab.interview,
        label: 'AI 면접',
        state: '완료했습니다',
        action: '보기',
        tone: _Tone.done,
      ),
      InterviewStatus.expired => const _Line(
        tab: ApplicantTab.interview,
        label: 'AI 면접',
        state: '기한이 지났습니다',
        action: '보기',
      ),
    };
  }

  _Line _statusLine() {
    final s = _status;
    return _Line(
      tab: ApplicantTab.more,
      label: '지원 현황',
      // 서버가 준 말을 그대로 쓴다 — 내부 단계값으로 되돌려 우리 색을 칠하면
      // 담당자가 통보하기 전에 화면이 먼저 말하게 된다
      state: s?.stageLabel ?? '아직 없습니다',
      action: s == null ? '' : '보기',
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }

    // 이름·공고는 받아 온 것 중 아무거나 — 넷 다 같은 사람 것이다
    final name =
        _status?.applicantName ??
        _interview?.applicantName ??
        _schedule?.applicantName ??
        _aptitude?.applicantName;
    final posting =
        _status?.postingTitle ??
        _interview?.postingTitle ??
        _schedule?.postingTitle ??
        _aptitude?.postingTitle;

    if (name == null) {
      return const ApplicantMissing(what: '받은 링크');
    }

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(AppSpace.s4),
        children: [
          Text(
            posting ?? '',
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.sm,
              color: AppColors.textSub,
            ),
          ),
          const SizedBox(height: AppSpace.s1),
          Text(
            '$name님',
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.h1,
              fontWeight: AppType.wSemiBold,
              color: AppColors.text,
              shadows: AppTextShadow.heading,
            ),
          ),
          const SizedBox(height: AppSpace.s5),

          for (final line in _lines) ...[
            _SummaryCard(line: line, onOpen: () => widget.onOpen(line.tab)),
            const SizedBox(height: AppSpace.s3),
          ],
        ],
      ),
    );
  }
}

class _SummaryCard extends StatelessWidget {
  const _SummaryCard({required this.line, required this.onOpen});

  final _Line line;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final todo = line.tone == _Tone.todo;
    return Material(
      color: AppColors.bgElev,
      shape: const RoundedRectangleBorder(
        borderRadius: AppShape.card,
        side: BorderSide(color: AppColors.border, width: AppShape.borderW),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        // 갈 곳이 없으면 눌리지 않는다 — 눌러도 아무 일 없는 카드는 고장 같다
        onTap: line.action.isEmpty ? null : onOpen,
        highlightColor: AppColors.bgSunken,
        splashColor: AppColors.bgSunken,
        child: Padding(
          padding: const EdgeInsets.all(AppSpace.s4),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      line.label,
                      style: const TextStyle(
                        fontFamily: AppType.fontFamily,
                        fontSize: AppType.body,
                        fontWeight: AppType.wSemiBold,
                        color: AppColors.text,
                      ),
                    ),
                    const SizedBox(height: AppSpace.s2),
                    Text(
                      line.state,
                      style: TextStyle(
                        fontFamily: AppType.fontFamily,
                        fontSize: AppType.sm,
                        color: switch (line.tone) {
                          _Tone.todo => AppColors.accentText,
                          _Tone.done => AppColors.okText,
                          _Tone.quiet => AppColors.textSub,
                        },
                      ),
                    ),
                  ],
                ),
              ),
              if (line.action.isNotEmpty) ...[
                const SizedBox(width: AppSpace.s3),
                // 할 일이 있는 줄만 채운다 — 눈에 먼저 들어야 한다
                Container(
                  height: 32,
                  padding: const EdgeInsets.symmetric(horizontal: AppSpace.s3),
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: todo ? AppColors.accentFill : AppColors.bgSunken,
                    borderRadius: AppShape.ctl,
                    border: todo
                        ? null
                        : Border.all(
                            color: AppColors.border,
                            width: AppShape.borderW,
                          ),
                  ),
                  child: Text(
                    line.action,
                    style: TextStyle(
                      fontFamily: AppType.fontFamily,
                      fontSize: AppType.caption,
                      fontWeight: AppType.wSemiBold,
                      color: todo ? AppColors.onAccent : AppColors.text,
                      shadows: todo ? AppTextShadow.onFill : null,
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
