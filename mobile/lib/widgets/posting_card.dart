/// 공고 카드 — 시안(2026-08-28) 5번. 앱 첫 화면의 목록 항목이다.
///
/// 시안이 정한 것:
/// - **긴 공고명은 두 줄까지** (`line-clamp: 2` + `word-break: keep-all`).
///   한 줄로 자르면 어느 공고인지 구분이 안 된다. 카드 높이가 들쭉날쭉해도
///   자르는 편이 낫다 (05-design §7 극단값)
/// - **상태는 칩 + 마감일 두 겹.** 색을 못 봐도 마감 여부가 읽힌다
/// - 카드마다 퍼널 막대 — 공고를 열지 않아도 어디에 사람이 몰려 있는지 보인다
///
/// 치수(시안): 카드 여백 16dp · 카드 최소 높이 88dp 이상
library;

import 'package:flutter/material.dart';

import '../models/job_posting.dart';
import '../models/stage.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';
import 'funnel_bar.dart';

class PostingCard extends StatelessWidget {
  const PostingCard({
    super.key,
    required this.posting,
    required this.counts,
    this.onTap,
    this.today,
  });

  final JobPosting posting;

  /// 단계 → 인원. 총원과 퍼널 비율을 여기서 뽑는다
  final Map<Stage, int> counts;

  final VoidCallback? onTap;

  /// 테스트에서 오늘 날짜를 고정하기 위한 구멍. 비우면 실제 오늘.
  final DateTime? today;

  @override
  Widget build(BuildContext context) {
    final total = counts.values.fold(0, (a, b) => a + b);
    final deadline = posting.deadlineOrDate(today ?? DateTime.now());

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
          constraints: const BoxConstraints(minHeight: 88),
          padding: const EdgeInsets.all(AppSpace.s4),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                posting.title,
                // 시안: 두 줄까지. 한 줄로 자르면 어느 공고인지 구분이 안 된다
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.h2,
                  fontWeight: FontWeight.w700,
                  color: AppColors.text,
                  shadows: AppTextShadow.heading,
                ),
              ),

              const SizedBox(height: AppSpace.s3),
              Row(
                children: [
                  _StatusChip(status: posting.status),
                  const SizedBox(width: AppSpace.s2),
                  Text(
                    formatCount(total),
                    softWrap: false,
                    style: const TextStyle(
                      fontFamily: AppType.fontFamily,
                      fontSize: AppType.num,
                      color: AppColors.text,
                      fontFeatures: AppType.tabularNums,
                    ),
                  ),
                  const Spacer(),
                  // 마감일이 없으면(상시 접수) 아무것도 그리지 않는다 — ERD 비고
                  if (deadline != null)
                    Text(
                      deadline,
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

              const SizedBox(height: AppSpace.s3),
              FunnelBar(counts: counts),
            ],
          ),
        ),
      ),
    );
  }
}

/// 공고 상태 칩 — 시안 5번.
/// 진행중만 연두, 나머지는 무채 (05-design §1 "색은 판단에만"과 같은 결).
class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.status});

  final PostingStatus status;

  @override
  Widget build(BuildContext context) {
    final (fg, border, bg) = switch (status) {
      PostingStatus.open => (
        AppColors.leaf,
        AppColors.sprout,
        AppColors.sproutSoft,
      ),
      _ => (AppColors.textSub, AppColors.border, AppColors.bgElev),
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
        status.label,
        softWrap: false,
        style: TextStyle(
          fontFamily: AppType.fontFamily,
          fontSize: AppType.caption,
          fontWeight: AppType.wSemiBold,
          color: fg,
        ),
      ),
    );
  }
}
