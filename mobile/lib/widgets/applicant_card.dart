/// 지원자 카드 — `mockup-mobile.html` 의 `.mcard` 를 옮긴 것.
///
/// 모바일은 칸반 카드를 드래그하지 않는다(05-design §9). 카드를 누르면 상세가 열리고,
/// 단계 변경은 거기 버튼으로 한다.
library;

import 'package:flutter/material.dart';

import '../models/applicant.dart';
import '../models/stage.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';

class ApplicantCard extends StatelessWidget {
  const ApplicantCard({super.key, required this.applicant, this.onTap});

  final Applicant applicant;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.bgElev,
      shape: const RoundedRectangleBorder(
        borderRadius: AppShape.card,
        side: BorderSide(color: AppColors.border, width: AppShape.borderW),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        // §5: 모바일은 hover 없음 전제 — press 만 정의한다
        highlightColor: AppColors.bgSunken,
        splashColor: AppColors.bgSunken,
        child: Container(
          constraints: const BoxConstraints(minHeight: 72),
          padding: const EdgeInsets.all(AppSpace.s3),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.baseline,
                textBaseline: TextBaseline.alphabetic,
                children: [
                  // 05-design §7: 긴 이름은 한 줄 ellipsis. 극단값 카드가 이걸 검증한다
                  Expanded(
                    child: Text(
                      applicant.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      softWrap: false,
                      style: const TextStyle(
                        fontFamily: AppType.fontFamily,
                        fontSize: AppType.body,
                        fontWeight: AppType.wSemiBold,
                        color: AppColors.text,
                      ),
                    ),
                  ),
                  const SizedBox(width: AppSpace.s2),
                  _StageLabel(stage: applicant.currentStage),
                ],
              ),

              const SizedBox(height: AppSpace.s2),
              Text(
                applicant.summaryLine,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                softWrap: false,
                style: const TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.sm,
                  color: AppColors.textSub,
                ),
              ),

              const SizedBox(height: AppSpace.s1),
              Text(
                formatDate(applicant.createdAt),
                softWrap: false,
                style: const TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.caption,
                  color: AppColors.textSub,
                  fontFeatures: AppType.tabularNums,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// 단계 라벨 — 05-design §1 **색은 판단에만.**
///
/// 진행 중(접수·서류·면접)은 무채색 + 라벨뿐이고,
/// **합격만 연두, 불합격만 적갈**로 굵게 쓴다. 판단 전에는 색을 주지 않는다.
class _StageLabel extends StatelessWidget {
  const _StageLabel({required this.stage});

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
