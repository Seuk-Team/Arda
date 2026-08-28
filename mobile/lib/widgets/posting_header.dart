/// 공고명 + 마감 D-day — `mockup-mobile.html` 의 `.mposting` 을 옮긴 것.
///
/// 어느 공고의 지원자를 보고 있는지 알려 주는 줄이다.
/// 공고 리스트 화면이 생기면 거기서 고른 공고가 여기로 넘어온다.
library;

import 'package:flutter/material.dart';

import '../models/job_posting.dart';
import '../theme/tokens.dart';

class PostingHeader extends StatelessWidget {
  const PostingHeader({super.key, required this.posting, this.today});

  final JobPosting posting;

  /// 테스트에서 오늘 날짜를 고정하기 위한 구멍. 비우면 실제 오늘.
  final DateTime? today;

  @override
  Widget build(BuildContext context) {
    final deadline = posting.deadlineLabel(today ?? DateTime.now());

    return Container(
      padding: const EdgeInsets.all(AppSpace.s3),
      decoration: const BoxDecoration(
        color: AppColors.bgElev,
        border: Border(
          bottom: BorderSide(color: AppColors.border, width: AppShape.borderW),
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.baseline,
        textBaseline: TextBaseline.alphabetic,
        children: [
          // 05-design §7: 긴 공고명은 한 줄 ellipsis 로 자른다
          Expanded(
            child: Text(
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
          ),

          // 마감일이 없으면(상시 접수) 아무것도 그리지 않는다 — ERD 비고
          if (deadline != null) ...[
            const SizedBox(width: AppSpace.s3),
            Text(
              deadline,
              // §2: 수치·날짜는 자리 폭 고정. 줄바꿈되면 버그다
              softWrap: false,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.num,
                color: AppColors.textSub,
                fontFeatures: AppType.tabularNums,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
