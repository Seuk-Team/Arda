import 'package:flutter/material.dart';

import '../data/mock_data.dart';
import '../models/applicant.dart';
import '../models/stage.dart';
import '../models/stage_history.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';
import '../widgets/app_top_bar.dart';

/// 단계 이력 — 시안(2026-08-28) 2번.
///
/// **어느 목업에도 없던 화면이다.** 서버가 `stage_history` 에 이전 단계·다음 단계·
/// 바꾼 사람·시각·사유를 남기고 있어, 그대로 시간순으로 편다.
///
/// 왜 표가 아니라 레일인가 (시안):
/// 폰 너비에서 표는 열이 눌린다. 레일은 한 열이라 눌릴 곳이 없다.
/// **최신이 위** — 지금 상태를 먼저 본다.
///
/// 치수(시안): 항목 최소 72dp(두 줄 목록) · 레일 24dp 열 · 점 12dp
class StageHistoryScreen extends StatelessWidget {
  const StageHistoryScreen({
    super.key,
    required this.applicant,
    required this.postingTitle,
  });

  final Applicant applicant;
  final String postingTitle;

  @override
  Widget build(BuildContext context) {
    final entries = mockStageHistory[applicant.id] ?? const <StageHistory>[];

    return Scaffold(
      appBar: const AppTopBar(title: '단계 이력', showBack: true),
      body: ListView(
        padding: const EdgeInsets.all(AppSpace.s4),
        children: [
          Text(
            '${applicant.name} · $postingTitle',
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.sm,
              color: AppColors.textSub,
            ),
          ),
          const SizedBox(height: AppSpace.s5),

          for (final (i, e) in entries.indexed)
            _Entry(entry: e, isFirst: i == 0, isLast: i == entries.length - 1),
        ],
      ),
    );
  }
}

class _Entry extends StatelessWidget {
  const _Entry({
    required this.entry,
    required this.isFirst,
    required this.isLast,
  });

  final StageHistory entry;
  final bool isFirst;
  final bool isLast;

  /// 시안: 레일 24dp 열 · 점 12dp
  static const _railWidth = 24.0;
  static const _dotSize = 12.0;

  /// 05-design §1 **색은 판단에만.**
  /// 진행 중은 무채, 합격만 연두, 불합격만 적갈.
  Color get _dotColor => switch (entry.toStage) {
    Stage.accepted => AppColors.sprout,
    Stage.rejected => AppColors.danger,
    _ => AppColors.neutral,
  };

  @override
  Widget build(BuildContext context) {
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(
            width: _railWidth,
            child: Column(
              children: [
                // 첫 항목 위로는 선을 긋지 않는다
                SizedBox(
                  height: 4,
                  child: isFirst ? null : const Center(child: _Rail()),
                ),
                Container(
                  width: _dotSize,
                  height: _dotSize,
                  decoration: BoxDecoration(
                    color: _dotColor,
                    shape: BoxShape.circle,
                  ),
                ),
                // 마지막 항목 아래로도 긋지 않는다
                Expanded(
                  child: isLast
                      ? const SizedBox()
                      : const Center(child: _Rail()),
                ),
              ],
            ),
          ),
          const SizedBox(width: AppSpace.s3),

          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(bottom: AppSpace.s5),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.baseline,
                    textBaseline: TextBaseline.alphabetic,
                    children: [
                      Text(
                        entry.toStage.label,
                        softWrap: false,
                        style: const TextStyle(
                          fontFamily: AppType.fontFamily,
                          fontSize: AppType.body,
                          fontWeight: AppType.wSemiBold,
                          color: AppColors.text,
                        ),
                      ),
                      // 시안: "어디에서 왔는지"를 같이 적는다.
                      // 단계 이름만 나열하면 되돌린 건지 전진한 건지 구분되지 않는다
                      if (entry.fromLabel != null) ...[
                        const SizedBox(width: AppSpace.s2),
                        Flexible(
                          child: Text(
                            entry.fromLabel!,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            softWrap: false,
                            style: const TextStyle(
                              fontFamily: AppType.fontFamily,
                              fontSize: AppType.caption,
                              color: AppColors.textSub,
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),

                  const SizedBox(height: AppSpace.s1),
                  Text(
                    '${formatDateTime(entry.createdAt)} · ${entry.actorLabel}',
                    style: const TextStyle(
                      fontFamily: AppType.fontFamily,
                      fontSize: AppType.num,
                      color: AppColors.textSub,
                      fontFeatures: AppType.tabularNums,
                    ),
                  ),

                  // 시안: 메일 발송 여부를 남긴다.
                  // "메일이 갔나?"는 단계 이력을 여는 가장 흔한 이유다
                  // 서버가 이 값을 주지 않으면(null) 아무 말도 하지 않는다 —
                  // 메일이 갔는지 모르면서 "갔다" 도 "안 갔다" 도 쓸 수 없다
                  if (entry.mailQueued ?? false) ...[
                    const SizedBox(height: AppSpace.s1),
                    Row(
                      children: [
                        const Icon(
                          Icons.mail_outline,
                          size: 14,
                          color: AppColors.textSub,
                        ),
                        const SizedBox(width: AppSpace.s1),
                        Flexible(
                          child: Text(
                            '${entry.toStage.label} 안내 메일 발송됨',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              fontFamily: AppType.fontFamily,
                              fontSize: AppType.caption,
                              color: AppColors.textSub,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],

                  // 시안: 불합격 사유는 인용 블록 — 적갈 왼쪽 선으로 본문과 구분한다
                  if (entry.reason != null && entry.reason!.isNotEmpty) ...[
                    const SizedBox(height: AppSpace.s2),
                    Container(
                      padding: const EdgeInsets.only(left: AppSpace.s3),
                      decoration: const BoxDecoration(
                        border: Border(
                          left: BorderSide(color: AppColors.danger, width: 2),
                        ),
                      ),
                      child: Text(
                        entry.reason!,
                        style: const TextStyle(
                          fontFamily: AppType.fontFamily,
                          fontSize: AppType.sm,
                          color: AppColors.text,
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// 항목을 잇는 세로 선.
class _Rail extends StatelessWidget {
  const _Rail();

  @override
  Widget build(BuildContext context) {
    return const SizedBox(
      width: AppShape.borderW,
      child: DecoratedBox(
        decoration: BoxDecoration(color: AppColors.border),
        child: SizedBox.expand(),
      ),
    );
  }
}
