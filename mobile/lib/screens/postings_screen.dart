import 'package:flutter/material.dart';

import '../data/mock_data.dart';
import '../routes.dart';
import '../theme/tokens.dart';
import '../widgets/posting_card.dart';

/// 채용 공고 목록 — 시안(2026-08-28) 5번.
///
/// 웹은 `공고 → 그 공고의 지원자` 순이고(05-design §0.5 화면 지도),
/// 앱이 지원자에서 시작하면 지금 어느 공고를 보는 중인지가 화면에 없다.
///
/// **본문만 그린다.** 상단 바·하단 탭바는 [HomeShell] 이 준다(조각 2) —
/// 탭을 옮겨도 껍데기는 그대로 있고 이 자리만 바뀌어야 하기 때문이다.
///
/// **아직 없는 것** — loading / empty / error 3종(05-design §6).
/// 완성의 정의는 후속 조각으로 누적해 채운다(§0-5).
class PostingsScreen extends StatelessWidget {
  const PostingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      // 시안: 화면 여백 16dp · 카드 사이 12dp
      padding: const EdgeInsets.all(AppSpace.s4),
      itemCount: mockPostings.length,
      separatorBuilder: (_, _) => const SizedBox(height: AppSpace.s3),
      itemBuilder: (_, i) {
        final posting = mockPostings[i];
        return PostingCard(
          posting: posting,
          counts: postingCounts(posting.id),
          onTap: () => Navigator.pushNamed(
            context,
            Routes.applicants,
            arguments: posting,
          ),
        );
      },
    );
  }
}
