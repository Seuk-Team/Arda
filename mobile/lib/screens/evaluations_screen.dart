import 'package:flutter/material.dart';

import '../data/mock_data.dart';
import '../models/applicant.dart';
import '../models/evaluation.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';
import '../widgets/app_top_bar.dart';

/// 평가 목록 — 시안(2026-08-28) 3번.
///
/// 웹에는 있는데 폰에서 놓을 자리가 없던 것이다. 상세 화면 안의 한 섹션이 아니라
/// **별도 화면**으로 뺐다 — 코멘트가 길어 상세에 끼우면 지원 정보가 아래로 밀린다.
///
/// **평균을 먼저, 개별을 다음에.** 스크롤 없이 보이는 첫 화면에 판단에 쓰는
/// 값(평균·인원)을 놓고, 근거인 코멘트는 그 아래로 둔다.
///
/// 치수(시안): 평균 블록 여백 16dp · 평가 항목 최소 72dp
class EvaluationsScreen extends StatelessWidget {
  const EvaluationsScreen({super.key, required this.applicant});

  final Applicant applicant;

  @override
  Widget build(BuildContext context) {
    final summary =
        mockEvaluations[applicant.id] ?? const EvaluationSummary(items: []);

    return Scaffold(
      appBar: const AppTopBar(title: '평가', showBack: true),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _Average(summary: summary),
          Expanded(
            child: ListView.separated(
              padding: const EdgeInsets.all(AppSpace.s4),
              itemCount: summary.items.length,
              separatorBuilder: (_, _) => const Divider(height: AppSpace.s5),
              itemBuilder: (_, i) => _EvaluationItem(item: summary.items[i]),
            ),
          ),
        ],
      ),
    );
  }
}

/// 평균 + 점수 분포 — 시안: 평균 4.3이 "4·4·5"인지 "3·5·5"인지는 다른 이야기다.
class _Average extends StatelessWidget {
  const _Average({required this.summary});

  final EvaluationSummary summary;

  @override
  Widget build(BuildContext context) {
    final avg = summary.avgScore;

    return Container(
      padding: const EdgeInsets.all(AppSpace.s4),
      decoration: const BoxDecoration(
        color: AppColors.bgElev,
        border: Border(
          bottom: BorderSide(color: AppColors.border, width: AppShape.borderW),
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.baseline,
                textBaseline: TextBaseline.alphabetic,
                children: [
                  Text(
                    avg?.toStringAsFixed(1) ?? '—',
                    // 시안은 40dp 를 제안했으나 05-design §2 스케일(26 이하)에
                    // 없는 값이라 display 로 뒀다. 40 을 쓰려면 토큰 추가가
                    // 필요하다(§0-1, 팀장 승인) — 시안도 "확인 필요"로 표시했다
                    style: const TextStyle(
                      fontFamily: AppType.fontFamily,
                      fontSize: AppType.display,
                      fontWeight: FontWeight.w700,
                      color: AppColors.text,
                      shadows: AppTextShadow.heading,
                      fontFeatures: AppType.tabularNums,
                    ),
                  ),
                  const Text(
                    ' / 5',
                    style: TextStyle(
                      fontFamily: AppType.fontFamily,
                      fontSize: AppType.sm,
                      color: AppColors.textSub,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpace.s1),
              Text(
                summary.count == 0
                    ? '아직 평가가 없습니다'
                    : '${formatCount(summary.count)}이 평가했습니다',
                softWrap: false,
                style: const TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.sm,
                  color: AppColors.textSub,
                ),
              ),
            ],
          ),

          if (summary.count > 0) ...[
            const SizedBox(width: AppSpace.s5),
            Expanded(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  for (final entry in summary.distribution.entries)
                    if (entry.key >= 3)
                      _DistributionRow(
                        score: entry.key,
                        count: entry.value,
                        total: summary.count,
                      ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// 점수 한 줄 — 시안: 막대 옆에 숫자를 같이 적어 색·길이를 못 읽어도 값이 전달된다.
class _DistributionRow extends StatelessWidget {
  const _DistributionRow({
    required this.score,
    required this.count,
    required this.total,
  });

  final int score;
  final int count;
  final int total;

  @override
  Widget build(BuildContext context) {
    const numberStyle = TextStyle(
      fontFamily: AppType.fontFamily,
      fontSize: AppType.caption,
      color: AppColors.textSub,
      fontFeatures: AppType.tabularNums,
    );

    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpace.s1),
      child: Row(
        children: [
          Text('$score', style: numberStyle),
          const SizedBox(width: AppSpace.s2),
          Expanded(
            child: ClipRRect(
              borderRadius: AppShape.pill,
              child: SizedBox(
                height: 4,
                child: Row(
                  // ColoredBox 는 느슨한 제약에서 높이 0 을 고른다 — 퍼널 바와 같은 함정
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (count > 0)
                      Expanded(
                        flex: count,
                        // 05-design §1: **점수에 색을 쓰지 않는다.**
                        // 평가 점수는 아직 판단이 아니라 재료다
                        child: const DecoratedBox(
                          decoration: BoxDecoration(color: AppColors.neutral),
                        ),
                      ),
                    if (total - count > 0)
                      Expanded(
                        flex: total - count,
                        child: const DecoratedBox(
                          decoration: BoxDecoration(color: AppColors.bgSunken),
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(width: AppSpace.s2),
          Text('$count', style: numberStyle),
        ],
      ),
    );
  }
}

/// 평가 한 건 — 시안: 항목 최소 72dp.
class _EvaluationItem extends StatelessWidget {
  const _EvaluationItem({required this.item});

  final Evaluation item;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(minHeight: 72),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              // 이름을 못 받으면 점수만 남는다 — 서버는 `evaluator_id` 만 주고
              // "평가자 7번" 은 아무 의미가 없다 (2026-09-02 실측)
              if (item.evaluatorName != null) ...[
                Text(
                  item.evaluatorName!,
                  softWrap: false,
                  style: const TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.body,
                    fontWeight: AppType.wSemiBold,
                    color: AppColors.text,
                  ),
                ),
                const SizedBox(width: AppSpace.s2),
                // §1: 점수에 색을 쓰지 않는다
                const Icon(Icons.circle, size: 6, color: AppColors.neutral),
                const SizedBox(width: AppSpace.s1),
              ],
              Text(
                '${item.score}',
                style: const TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.num,
                  fontWeight: AppType.wSemiBold,
                  color: AppColors.text,
                  fontFeatures: AppType.tabularNums,
                ),
              ),
              const Spacer(),
              Text(
                formatDate(item.createdAt),
                softWrap: false,
                style: const TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.num,
                  color: AppColors.textSub,
                  fontFeatures: AppType.tabularNums,
                ),
              ),
            ],
          ),
          if (item.comment != null && item.comment!.isNotEmpty) ...[
            const SizedBox(height: AppSpace.s2),
            Text(
              item.comment!,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.sm,
                color: AppColors.text,
                height: 1.5,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
