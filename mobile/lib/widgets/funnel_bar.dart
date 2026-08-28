/// 퍼널 바 — 시안(2026-08-28) 4번. 단계별 인원 **비율**만 보여 주는 막대다.
///
/// 웹(`mockup.html` `.funnel`)은 막대 아래에 단계 이름과 인원을 나란히 적지만,
/// 폰 너비에는 그 라벨이 들어가지 않는다. 시안의 결정:
///
/// - **막대는 비율만, 숫자는 탭이** 나눠 맡는다. 라벨을 두 번 그리지 않는다.
/// - **툴팁을 달지 않는다** — 05-design §5, 모바일은 hover 가 없다.
///   눌러야만 보이는 정보는 없는 정보와 같다.
/// - **필터로 만들지 않는다** — 8dp 막대는 48dp 터치 타깃을 못 채운다.
///   거르는 일은 탭이 맡고, 막대는 읽기 전용이다.
library;

import 'package:flutter/material.dart';

import '../models/stage.dart';
import '../theme/tokens.dart';

class FunnelBar extends StatelessWidget {
  const FunnelBar({super.key, required this.counts});

  /// 단계 → 인원
  final Map<Stage, int> counts;

  /// 시안: 막대 8dp
  static const _height = 8.0;

  @override
  Widget build(BuildContext context) {
    final total = counts.values.fold(0, (a, b) => a + b);

    return Semantics(
      // 화면 낭독기에는 비율 대신 실제 숫자를 읽어 준다 (05-design §10)
      label: [
        for (final s in Stage.values)
          if ((counts[s] ?? 0) > 0) '${s.label} ${counts[s]}명',
      ].join(', '),
      excludeSemantics: true,
      child: ClipRRect(
        borderRadius: AppShape.pill,
        child: SizedBox(
          height: _height,
          child: total == 0
              // 아무도 없으면 빈 트랙만 그린다
              ? const DecoratedBox(
                  decoration: BoxDecoration(color: AppColors.bgSunken),
                  child: SizedBox.expand(),
                )
              : Row(
                  // ColoredBox 는 자식이 없으면 느슨한 제약에서 가장 작은 높이(0)를
                  // 고른다. Row 기본 정렬(center)로 두면 막대가 사라진다
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    for (final stage in Stage.values)
                      if ((counts[stage] ?? 0) > 0)
                        Expanded(
                          flex: counts[stage]!,
                          child: DecoratedBox(
                            decoration: BoxDecoration(color: _colorOf(stage)),
                          ),
                        ),
                  ],
                ),
        ),
      ),
    );
  }

  /// 05-design §1 — 진행 구간은 무채 램프(흐름 그래프 한정 허용),
  /// **합격만 연두, 불합격만 적갈.**
  static Color _colorOf(Stage stage) => switch (stage) {
    Stage.applied => AppColors.funnelRamp[0],
    Stage.screening => AppColors.funnelRamp[1],
    Stage.interview => AppColors.funnelRamp[2],
    Stage.accepted => AppColors.sprout,
    Stage.rejected => AppColors.danger,
  };
}
