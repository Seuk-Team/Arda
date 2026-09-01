/// 공고 헤더 — 시안(2026-08-28) 4번.
///
/// 공고명 → `마감 D-12 · 총 22명` → 퍼널 바 순으로 쌓는다.
/// 목업(`.mposting`)은 공고명과 마감을 한 줄에 나란히 뒀지만, 시안이 총원과
/// 퍼널 바를 더하면서 세로로 풀렸다.
library;

import 'package:flutter/material.dart';

import '../models/job_posting.dart';
import '../models/stage.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';
import 'funnel_bar.dart';

class PostingHeader extends StatelessWidget {
  const PostingHeader({
    super.key,
    required this.posting,
    required this.counts,
    this.today,
  });

  final JobPosting posting;

  /// 단계 → 인원. 총원과 퍼널 비율을 여기서 뽑는다
  final Map<Stage, int> counts;

  /// 테스트에서 오늘 날짜를 고정하기 위한 구멍. 비우면 실제 오늘.
  final DateTime? today;

  @override
  Widget build(BuildContext context) {
    final deadline = posting.deadlineLabel(today ?? DateTime.now());
    final total = counts.values.fold(0, (a, b) => a + b);

    // 마감일이 없으면(상시 접수) 그 조각을 빼고 총원만 적는다 — ERD 비고
    final meta = [?deadline, '총 ${formatCount(total)}'].join(' · ');

    return Container(
      padding: const EdgeInsets.all(AppSpace.s4),
      decoration: const BoxDecoration(color: AppColors.bgElev),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          // 05-design §7: 긴 공고명은 한 줄 ellipsis 로 자른다
          Text(
            posting.title,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            softWrap: false,
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.h2,
              fontWeight: FontWeight.w700,
              color: AppColors.text,
              shadows: AppTextShadow.heading,
            ),
          ),

          const SizedBox(height: AppSpace.s1),
          Text(
            meta,
            // §2: 수치·날짜는 자리 폭 고정. 줄바꿈되면 버그다
            softWrap: false,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.num,
              color: AppColors.textSub,
              fontFeatures: AppType.tabularNums,
            ),
          ),

          const SizedBox(height: AppSpace.s3),
          FunnelBar(counts: counts),
        ],
      ),
    );
  }
}
