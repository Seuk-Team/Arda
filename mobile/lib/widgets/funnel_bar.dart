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
  const FunnelBar({
    super.key,
    required this.counts,
    this.stages = Stage.values,
    this.keepEmptySegments = false,
  });

  /// 단계 → 인원
  final Map<Stage, int> counts;

  /// 그릴 단계와 순서. 기본은 전 단계.
  ///
  /// 대시보드 레일은 **접수~합격 4단**이다 — 05-design §0.5 가 그렇게 정했다.
  /// 공고 카드(시안 4번)는 지금까지대로 불합격까지 다섯 구간을 그린다.
  final List<Stage> stages;

  /// 0건 구간도 [_minSegment] 만큼 남길지.
  ///
  /// 05-design §0.5: "레일 구간 폭은 `minmax(6px, n fr)` — **0건 구간도 6px 남긴다**
  /// (폭 0이면 단계가 사라져 몇 단인지 안 보인다)". 대시보드 레일이 이 규칙을 쓴다.
  final bool keepEmptySegments;

  /// 시안: 막대 8dp
  static const _height = 8.0;

  /// §0.5 가 정한 구간 최소 폭
  static const _minSegment = 6.0;

  @override
  Widget build(BuildContext context) {
    final total = stages.fold(0, (sum, s) => sum + (counts[s] ?? 0));

    return Semantics(
      // 화면 낭독기에는 비율 대신 실제 숫자를 읽어 준다 (05-design §10)
      label: [
        for (final s in stages)
          if ((counts[s] ?? 0) > 0) '${s.label} ${counts[s]}명',
      ].join(', '),
      excludeSemantics: true,
      child: ClipRRect(
        borderRadius: AppShape.pill,
        child: SizedBox(
          height: _height,
          child: keepEmptySegments
              ? _FixedWidthRail(
                  counts: counts,
                  stages: stages,
                  total: total,
                  minSegment: _minSegment,
                )
              : total == 0
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
                    for (final stage in stages)
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

  /// 대시보드 레일이 쓰는 색. 범례가 같은 색을 찍어야 해서 밖으로 연다.
  static Color colorOf(Stage stage) => _colorOf(stage);

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

/// 0건 구간도 살려 두는 레일 — 05-design §0.5 `minmax(6px, n fr)` 의 이식.
///
/// `Expanded(flex:)` 로는 최소 폭을 줄 수 없다(flex 0 은 폭 0 이 된다).
/// 폭을 직접 계산한다: 모든 구간에 먼저 [minSegment] 씩 떼어 주고, 남은 폭만
/// 인원 비율로 나눈다. 그래서 0건 구간도 6px 은 남고, 몇 단짜리 전형인지가
/// 인원과 무관하게 늘 읽힌다.
class _FixedWidthRail extends StatelessWidget {
  const _FixedWidthRail({
    required this.counts,
    required this.stages,
    required this.total,
    required this.minSegment,
  });

  final Map<Stage, int> counts;
  final List<Stage> stages;
  final int total;
  final double minSegment;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.maxWidth;
        final floor = minSegment * stages.length;
        // 6px 씩도 못 채울 만큼 좁으면 비율만으로 나눈다 — 넘쳐서 깨지는 것보다 낫다
        final spare = width > floor ? width - floor : 0.0;
        final base = width > floor ? minSegment : width / stages.length;

        return Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            for (final stage in stages)
              SizedBox(
                width:
                    base +
                    (total == 0 ? 0.0 : spare * (counts[stage] ?? 0) / total),
                child: DecoratedBox(
                  decoration: BoxDecoration(color: FunnelBar.colorOf(stage)),
                ),
              ),
          ],
        );
      },
    );
  }
}
