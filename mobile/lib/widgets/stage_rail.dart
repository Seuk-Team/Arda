/// 전형 레일 — 앱 UI 초안(2026-09-01) 지원자 상세 상단.
///
/// 이 사람이 접수 → 서류 → 면접 → 합격 중 어디까지 왔는지 한 줄로 보여 준다.
/// 퍼널 바(`funnel_bar.dart`)가 **여러 명의 분포**를 그리는 것과 달리, 여기는
/// **한 명의 위치**다 — 같은 4단이지만 읽는 방향이 다르다.
///
/// 색은 05-design §1 그대로: 지난 단계는 연두 워시, 지금 단계는 짙은 잎,
/// 남은 단계는 sunken. 새 색을 만들지 않았다.
///
/// **불합격이면 그리지 않는다.** 레일에 불합격 칸이 없고(초안이 4단),
/// 억지로 끼우면 "합격 다음이 불합격"처럼 읽힌다. 그 사람의 상태는 이름 옆
/// 단계 pill 이 이미 적갈로 말하고 있다.
library;

import 'package:flutter/material.dart';

import '../models/stage.dart';
import '../theme/tokens.dart';

class StageRail extends StatelessWidget {
  const StageRail({super.key, required this.current});

  final Stage current;

  /// 초안의 4단. 불합격은 레일 밖이다
  static const stages = [
    Stage.applied,
    Stage.screening,
    Stage.interview,
    Stage.accepted,
  ];

  /// 동그라미 지름
  static const _node = 24.0;

  /// 이 단계를 그릴지 — 불합격은 레일이 나오지 않는다
  static bool showsFor(Stage stage) => stages.contains(stage);

  @override
  Widget build(BuildContext context) {
    final currentIndex = stages.indexOf(current);

    return Semantics(
      label: '전형 ${stages.length}단계 중 ${currentIndex + 1}번째 — ${current.label}',
      excludeSemantics: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              for (var i = 0; i < stages.length; i++) ...[
                if (i > 0)
                  Expanded(
                    child: Container(
                      height: 2,
                      color: i <= currentIndex
                          ? AppColors.sprout
                          : AppColors.sunkenHover,
                    ),
                  ),
                _Node(index: i, currentIndex: currentIndex),
              ],
            ],
          ),
          const SizedBox(height: AppSpace.s2),
          Row(
            children: [
              for (var i = 0; i < stages.length; i++) ...[
                if (i > 0) const Spacer(),
                SizedBox(
                  // 동그라미 밑에 라벨을 맞춘다. 글자가 더 넓어 살짝 여유를 준다
                  width: _node + AppSpace.s5,
                  child: Text(
                    stages[i].label,
                    textAlign: i == 0
                        ? TextAlign.left
                        : i == stages.length - 1
                        ? TextAlign.right
                        : TextAlign.center,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    softWrap: false,
                    style: TextStyle(
                      fontFamily: AppType.fontFamily,
                      fontSize: AppType.caption,
                      fontWeight: i == currentIndex
                          ? AppType.wSemiBold
                          : AppType.wRegular,
                      color: i == currentIndex
                          ? AppColors.leaf
                          : AppColors.textSub,
                    ),
                  ),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }
}

class _Node extends StatelessWidget {
  const _Node({required this.index, required this.currentIndex});

  final int index;
  final int currentIndex;

  @override
  Widget build(BuildContext context) {
    final done = index < currentIndex;
    final now = index == currentIndex;

    final (bg, border, fg) = switch ((done, now)) {
      (true, _) => (AppColors.sproutSoft, AppColors.sprout, AppColors.leaf),
      (_, true) => (AppColors.leaf, AppColors.leaf, AppColors.bgElev),
      _ => (AppColors.bgSunken, AppColors.border, AppColors.textSub),
    };

    return Container(
      width: StageRail._node,
      height: StageRail._node,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: bg,
        shape: BoxShape.circle,
        border: Border.all(color: border, width: AppShape.borderW),
      ),
      child: done
          ? Icon(Icons.check, size: 14, color: fg)
          : Text(
              '${index + 1}',
              style: TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.caption,
                fontWeight: AppType.wSemiBold,
                fontFeatures: AppType.tabularNums,
                color: fg,
                // §2: 색 채움 위 밝은 글자엔 onFill 그림자
                shadows: now ? AppTextShadow.onFill : null,
              ),
            ),
    );
  }
}
