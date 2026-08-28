/// 단계 라벨 — 05-design §1 **색은 판단에만.**
///
/// 진행 중(접수·서류·면접)은 무채색 + 라벨뿐이고,
/// **합격만 연두, 불합격만 적갈**로 굵게 쓴다. 판단 전에는 색을 주지 않는다.
///
/// 목업의 `.stage-progress` / `.stage-accepted` / `.stage-rejected` 에 대응한다.
/// 카드와 상세 헤더가 같은 규격을 써야 해서 위젯으로 뺐다.
library;

import 'package:flutter/material.dart';

import '../models/stage.dart';
import '../theme/tokens.dart';

class StageLabel extends StatelessWidget {
  const StageLabel({super.key, required this.stage});

  final Stage stage;

  @override
  Widget build(BuildContext context) {
    final (color, weight) = switch (stage) {
      Stage.accepted => (AppColors.leaf, FontWeight.w700),
      Stage.rejected => (AppColors.danger, FontWeight.w700),
      _ => (AppColors.textSub, AppType.wRegular),
    };

    return Text(
      stage.label,
      // 단계는 한 줄 고정. 두 줄이 되면 버그다 (§2)
      softWrap: false,
      style: TextStyle(
        fontFamily: AppType.fontFamily,
        fontSize: AppType.sm,
        fontWeight: weight,
        color: color,
      ),
    );
  }
}
