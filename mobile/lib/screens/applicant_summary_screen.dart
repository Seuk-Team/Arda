/// 지원자 홈 — 전체 메뉴 요약 (2026-09-08).
///
/// 탭 넷이 지금 각각 어떤지 한 화면에 모은다. 지원자가 앱을 켜는 이유는
/// **"내가 지금 뭘 해야 하지"** 하나라, 홈은 그 답만 한다: 할 일이 있는 줄은
/// 채운 버튼으로, 끝났거나 기다리는 줄은 조용히.
///
/// **서버를 따로 부르지 않는다.** 셸이 받은 `GET /applicant/me` 하나에 단계도
/// 토큰도 상태도 다 들어 있다 — 줄마다 다시 물어보던 것을 걷어냈다.
///
/// 지원이 여럿이면 **전부 보여 준다.** 한 사람이 공고 여럿에 낼 수 있고
/// (동명이인 시연 계정이 그 경우다), 어느 지원의 면접인지 여기서 갈린다.
library;

import 'package:flutter/material.dart';

import '../models/applicant_me.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';
import 'applicant_shell.dart';

/// 할 일이 있는가. **색은 거들 뿐이고 글자가 늘 같이 있다**
enum _Tone { todo, done, quiet }

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

class ApplicantSummaryScreen extends StatelessWidget {
  const ApplicantSummaryScreen({
    super.key,
    required this.me,
    required this.onOpen,
    required this.onRefresh,
  });

  final ApplicantMe me;

  /// 탭을 옮겨 준다 — 요약은 자기가 어느 셸에 앉아 있는지 몰라야 한다
  final ValueChanged<ApplicantTab> onOpen;

  final Future<void> Function() onRefresh;

  @override
  Widget build(BuildContext context) {
    if (me.applications.isEmpty) {
      return const ApplicantMissing(what: '지원 내역');
    }

    return RefreshIndicator(
      onRefresh: onRefresh,
      child: ListView(
        padding: const EdgeInsets.all(AppSpace.s4),
        children: [
          Text(
            '${me.name}님',
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.h1,
              fontWeight: AppType.wSemiBold,
              color: AppColors.text,
              shadows: AppTextShadow.heading,
            ),
          ),
          const SizedBox(height: AppSpace.s1),
          Text(
            me.email,
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.sm,
              color: AppColors.textSub,
            ),
          ),
          const SizedBox(height: AppSpace.s5),

          for (final app in me.applications) ...[
            _ApplicationBlock(app: app, onOpen: onOpen),
            const SizedBox(height: AppSpace.s5),
          ],
        ],
      ),
    );
  }
}

/// 지원 한 건 — 공고·단계 머리와 그 아래 할 일 줄들
class _ApplicationBlock extends StatelessWidget {
  const _ApplicationBlock({required this.app, required this.onOpen});

  final MyApplication app;
  final ValueChanged<ApplicantTab> onOpen;

  List<_Line> get _lines => [_aptitude(), _schedule(), _interview()];

  _Line _aptitude() {
    if (app.aptitudes.isEmpty) {
      return const _Line(
        tab: ApplicantTab.aptitude,
        label: '인적성 검사',
        state: '아직 없습니다',
        action: '',
      );
    }
    // 낸 것(`done`)도 내려온다 (2026-09-09) — **끝난 것을 안 보여 주면
    // "완료"와 "아직 안 잡힘"이 같은 화면이 된다**
    final done = app.aptitudes.first.status == 'done';
    return _Line(
      tab: ApplicantTab.aptitude,
      label: '인적성 검사',
      state: done ? '제출했습니다' : '아직 안 냈습니다',
      // 낸 뒤에는 다시 들어갈 곳이 없다 — 문을 그리지 않는다
      action: done ? '' : '검사하기',
      tone: done ? _Tone.done : _Tone.todo,
    );
  }

  _Line _schedule() {
    if (app.schedules.isEmpty) {
      return const _Line(
        tab: ApplicantTab.schedule,
        label: '면접 시간',
        state: '아직 없습니다',
        action: '',
      );
    }
    // 일정만 `confirmed` 도 온다 — 확정 뒤에도 "언제로 잡혔는지" 볼 일이 있다
    final done = app.schedules.first.status == 'confirmed';
    return _Line(
      tab: ApplicantTab.schedule,
      label: '면접 시간',
      state: done ? '확정됐습니다' : '후보 시간을 골라 주세요',
      action: done ? '보기' : '시간 고르기',
      tone: done ? _Tone.done : _Tone.todo,
    );
  }

  _Line _interview() {
    if (app.interviews.isEmpty) {
      return const _Line(
        tab: ApplicantTab.interview,
        label: 'AI 면접',
        state: '아직 없습니다',
        action: '',
      );
    }
    // **끝난 것을 먼저 본다.** 면접을 여러 번 만들 수 있어(재발급) 목록에
    // 끝난 것과 새 것이 같이 올 수 있는데, 그럴 땐 **아직 할 일이 있는 쪽**이
    // 지원자가 알아야 하는 것이다.
    final open = app.interviews.where((i) => i.status != 'done');
    if (open.isEmpty) {
      return const _Line(
        tab: ApplicantTab.interview,
        label: 'AI 면접',
        state: '완료했습니다',
        // 끝난 면접은 다시 들어갈 수 없다 — 문을 그리지 않는다
        action: '',
        tone: _Tone.done,
      );
    }
    final going = open.first.status == 'in_progress';
    return _Line(
      tab: ApplicantTab.interview,
      label: 'AI 면접',
      state: going ? '진행 중입니다' : '아직 시작하지 않았습니다',
      action: going ? '이어서 보기' : '면접 보기',
      tone: _Tone.todo,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          app.postingTitle,
          style: const TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.body,
            fontWeight: AppType.wSemiBold,
            color: AppColors.text,
          ),
        ),
        const SizedBox(height: AppSpace.s1),
        Row(
          children: [
            // 서버가 준 말을 그대로 쓴다 — 내부 단계값으로 되돌려 우리 색을
            // 칠하면 담당자가 통보하기 전에 화면이 먼저 말하게 된다
            Text(
              app.stageLabel,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.sm,
                fontWeight: AppType.wSemiBold,
                color: AppColors.accentText,
              ),
            ),
            const SizedBox(width: AppSpace.s2),
            Text(
              '· ${formatDate(app.appliedAt)} 접수',
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.caption,
                fontFeatures: AppType.tabularNums,
                color: AppColors.textSub,
              ),
            ),
          ],
        ),
        const SizedBox(height: AppSpace.s3),

        for (final line in _lines) ...[
          _SummaryCard(line: line, onOpen: () => onOpen(line.tab)),
          const SizedBox(height: AppSpace.s2),
        ],
      ],
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
