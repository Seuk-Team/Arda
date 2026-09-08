/// 단계 칩 — 시안(2026-08-28)의 단계 표시. 목업의 글자 표기를 칩으로 올린 것이다.
///
/// 05-design §1 **색은 판단에만.**
/// 진행 중(접수·서류·면접)은 무채색, **합격만 연두, 불합격만 적갈.**
/// 판단 전에는 색을 주지 않는다.
///
/// 칩의 세부 규격(테두리·채움)은 시안에 수치가 없어 기존 토큰으로 채웠다 —
/// `--r-pill` · `--border` · §1 색. 시안과 다르면 여기만 고치면 된다.
library;

import 'package:flutter/material.dart';

import '../models/stage.dart';
import '../theme/tokens.dart';

class StageLabel extends StatelessWidget {
  const StageLabel({super.key, required this.stage});

  final Stage stage;

  @override
  Widget build(BuildContext context) {
    // (글자색, 테두리색, 채움색, 굵기)
    final (fg, border, bg, weight) = switch (stage) {
      // 2026-09-07 — 다크로 옮기면서 leaf/sprout 별칭이 시안을 가리키게 됐다.
      // 합격은 시안이 아니라 초록이다: 시안은 '강조', 초록은 '통과' 라
      // 뜻이 다르다. 새 이름으로 바로잡는다
      Stage.accepted => (
        AppColors.okText,
        AppColors.ok,
        AppColors.okSoft,
        FontWeight.w700,
      ),
      Stage.rejected => (
        AppColors.danger,
        AppColors.danger,
        AppColors.dangerSoft,
        FontWeight.w700,
      ),
      // 판단 전 — 색 없이 테두리만
      _ => (
        AppColors.textSub,
        AppColors.border,
        AppColors.bgElev,
        AppType.wRegular,
      ),
    };

    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpace.s2,
        vertical: AppSpace.s1,
      ),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: AppShape.pill,
        border: Border.fromBorderSide(
          BorderSide(color: border, width: AppShape.borderW),
        ),
      ),
      child: Text(
        stage.label,
        // 칩은 한 줄 고정. 두 줄이 되면 버그다 (§2)
        softWrap: false,
        style: TextStyle(
          fontFamily: AppType.fontFamily,
          fontSize: AppType.caption,
          fontWeight: weight,
          color: fg,
        ),
      ),
    );
  }
}
