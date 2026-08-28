import 'package:flutter/material.dart';

import '../data/mock_data.dart';
import '../models/applicant.dart';
import '../models/stage.dart';
import '../routes.dart';
import '../theme/tokens.dart';
import '../widgets/app_top_bar.dart';
import '../widgets/applicant_card.dart';
import '../widgets/posting_header.dart';
import '../widgets/stage_tabs.dart';

/// 공고 하나의 지원자 리스트. 현재의 첫 화면이다.
///
/// 화면 구성은 `frontend/mockups/mockup-mobile.html` 을 따른다:
/// 상단 바 → 공고명·마감 → 단계 탭 → 카드 리스트.
///
/// **아직 없는 것** — loading / empty / error 3종(05-design §6)과
/// 퍼널 바. 완성의 정의는 후속 조각으로 누적해 채운다(§0-5).
class ApplicantsScreen extends StatefulWidget {
  const ApplicantsScreen({super.key});

  @override
  State<ApplicantsScreen> createState() => _ApplicantsScreenState();
}

class _ApplicantsScreenState extends State<ApplicantsScreen> {
  /// 목업이 `지원 접수` 에 `.on` 을 붙여 둔 것을 그대로 따른다.
  Stage _selected = Stage.applied;

  /// role/app.md §3: 단계 탭은 **필터**다. 선택한 단계만 보여 준다.
  List<Applicant> get _visible =>
      mockApplicants.where((a) => a.currentStage == _selected).toList();

  @override
  Widget build(BuildContext context) {
    final applicants = _visible;

    return Scaffold(
      appBar: const AppTopBar(),
      body: Column(
        children: [
          PostingHeader(posting: mockPosting),
          StageTabs(
            selected: _selected,
            onSelected: (stage) => setState(() => _selected = stage),
          ),
          Expanded(
            // 목업 `.mlist` — 카드 사이 8px, 바깥 여백 12px
            child: ListView.separated(
              padding: const EdgeInsets.all(AppSpace.s3),
              itemCount: applicants.length,
              separatorBuilder: (_, _) => const SizedBox(height: AppSpace.s2),
              itemBuilder: (_, i) => ApplicantCard(
                applicant: applicants[i],
                onTap: () => Navigator.pushNamed(
                  context,
                  Routes.applicantDetail,
                  arguments: applicants[i],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
