import 'package:flutter/material.dart';

import '../data/mock_data.dart';
import '../models/applicant.dart';
import '../models/job_posting.dart';
import '../models/stage.dart';
import '../routes.dart';
import '../theme/tokens.dart';
import '../widgets/app_top_bar.dart';
import '../widgets/applicant_card.dart';
import '../widgets/posting_header.dart';
import '../widgets/stage_tabs.dart';

/// 한 공고의 지원자 리스트. 공고 리스트에서 공고를 골라 들어온다.
///
/// 화면 구성은 시안(2026-08-28) 4번:
/// 상단 바 → 공고명·마감·총원 → 퍼널 막대 → 단계 탭 → 카드 리스트.
///
/// **아직 없는 것** — loading / empty / error 3종(05-design §6)과
/// 검색. 완성의 정의는 후속 조각으로 누적해 채운다(§0-5).
class ApplicantsScreen extends StatefulWidget {
  const ApplicantsScreen({super.key, required this.posting});

  final JobPosting posting;

  @override
  State<ApplicantsScreen> createState() => _ApplicantsScreenState();
}

class _ApplicantsScreenState extends State<ApplicantsScreen> {
  /// 목업이 `지원 접수` 에 `.on` 을 붙여 둔 것을 그대로 따른다.
  Stage _selected = Stage.applied;

  /// 이 공고의 지원자. 목데이터는 1번 공고 것만 있다
  List<Applicant> get _all =>
      mockApplicants.where((a) => a.jobPostingId == widget.posting.id).toList();

  /// 단계별 인원 — 퍼널 바와 탭이 함께 쓴다
  Map<Stage, int> get _counts => stageCounts(_all);

  /// role/app.md §3: 단계 탭은 **필터**다. 선택한 단계만 보여 준다.
  List<Applicant> get _visible =>
      _all.where((a) => a.currentStage == _selected).toList();

  @override
  Widget build(BuildContext context) {
    final applicants = _visible;
    final counts = _counts;

    return Scaffold(
      appBar: const AppTopBar(title: '지원자', showBack: true),
      body: Column(
        children: [
          PostingHeader(posting: widget.posting, counts: counts),
          StageTabs(
            selected: _selected,
            onSelected: (stage) => setState(() => _selected = stage),
            counts: counts,
          ),
          Expanded(
            // 시안: 화면 여백 16dp · 카드 사이 12dp
            child: ListView.separated(
              padding: const EdgeInsets.all(AppSpace.s4),
              itemCount: applicants.length,
              separatorBuilder: (_, _) => const SizedBox(height: AppSpace.s3),
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
