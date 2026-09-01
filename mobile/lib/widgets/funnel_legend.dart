/// 퍼널 레일 범례 — [FunnelBar] 밑에 붙는 색 점 + 단계 + 건수.
///
/// 05-design §0.5: "단계별 건수는 **눈금이 아니라 범례**다: 색 점 + 라벨 + 건수를
/// **왼쪽부터 한 줄로 붙여 쓴다**(균등 분산하면 구간과 어긋나 눈금으로 오독된다)."
///
/// 대시보드 전형 현황과 공고 카드가 같이 쓴다 — §3 동종 요소 동일 규격.
library;

import 'package:flutter/material.dart';

import '../models/stage.dart';
import '../theme/tokens.dart';
import 'funnel_bar.dart';

class FunnelLegend extends StatelessWidget {
  const FunnelLegend({super.key, required this.counts, required this.stages});

  final Map<Stage, int> counts;

  /// 레일이 그린 것과 **같은 단계·같은 순서**여야 한다. 어긋나면 색과 숫자가 따로 논다
  final List<Stage> stages;

  /// 색 점 크기 — 레일 두께(8)와 같게 둔다
  static const _dot = 8.0;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: AppSpace.s3,
      runSpacing: AppSpace.s1,
      children: [
        for (final stage in stages)
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: _dot,
                height: _dot,
                decoration: BoxDecoration(
                  color: FunnelBar.colorOf(stage),
                  borderRadius: const BorderRadius.all(Radius.circular(2)),
                ),
              ),
              const SizedBox(width: AppSpace.s1),
              Text(
                stage.label,
                softWrap: false,
                style: const TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.caption,
                  color: AppColors.textSub,
                ),
              ),
              const SizedBox(width: AppSpace.s1),
              Text(
                '${counts[stage] ?? 0}',
                softWrap: false,
                style: const TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.caption,
                  fontWeight: AppType.wSemiBold,
                  fontFeatures: AppType.tabularNums,
                  color: AppColors.text,
                ),
              ),
            ],
          ),
      ],
    );
  }
}
