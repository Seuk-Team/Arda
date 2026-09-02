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
import '../widgets/search_field.dart';
import '../widgets/stage_tabs.dart';

/// 한 공고의 지원자 리스트. 공고 리스트에서 공고를 골라 들어온다.
///
/// 화면 구성은 시안(2026-08-28) 4번 + 검색(2026-09-02 추가):
/// 상단 바 → 공고명·마감·총원 → 퍼널 막대 → **검색** → 단계 탭 → 카드 리스트.
///
/// **아직 없는 것** — loading / error(05-design §6). 목데이터라 기다릴 것도
/// 실패할 것도 없다. 큐 8에서 API 가 붙을 때 함께 온다.
class ApplicantsScreen extends StatefulWidget {
  const ApplicantsScreen({super.key, required this.posting});

  final JobPosting posting;

  @override
  State<ApplicantsScreen> createState() => _ApplicantsScreenState();
}

class _ApplicantsScreenState extends State<ApplicantsScreen> {
  /// 목업이 `지원 접수` 에 `.on` 을 붙여 둔 것을 그대로 따른다.
  Stage _selected = Stage.applied;

  final _search = TextEditingController();
  String _query = '';

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  /// 이 공고의 지원자. 목데이터는 1번 공고 것만 있다
  List<Applicant> get _all =>
      mockApplicants.where((a) => a.jobPostingId == widget.posting.id).toList();

  /// 단계별 인원 — 퍼널 바와 탭이 함께 쓴다.
  /// **검색과 무관하게 전체를 센다** — 걸러진 수를 탭에 달면 검색어를 지우기
  /// 전까지 이 공고에 몇 명이 있는지 알 수 없다.
  Map<Stage, int> get _counts => stageCounts(_all);

  /// role/app.md §3: 단계 탭은 **필터**다. 선택한 단계만 보여 준다.
  /// 검색어가 있으면 그 안에서 이름으로 한 번 더 거른다.
  List<Applicant> get _visible {
    final stage = _all.where((a) => a.currentStage == _selected);
    if (_query.isEmpty) return stage.toList();

    final q = _query.toLowerCase();
    return stage.where((a) => a.name.toLowerCase().contains(q)).toList();
  }

  @override
  Widget build(BuildContext context) {
    final applicants = _visible;
    final counts = _counts;

    return Scaffold(
      appBar: const AppTopBar(title: '지원자', showBack: true),
      body: Column(
        children: [
          PostingHeader(posting: widget.posting, counts: counts),
          // 웹 PostingApplicants.tsx 의 "검색어 입력". 단계 탭 위에 둔다 —
          // 탭보다 넓은 범위를 거르는 것이라 위가 맞다
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpace.s4,
              AppSpace.s3,
              AppSpace.s4,
              0,
            ),
            child: SearchField(
              controller: _search,
              hintText: '이름 검색',
              onChanged: (v) => setState(() => _query = v.trim()),
              onClear: () => setState(() {
                _search.clear();
                _query = '';
              }),
            ),
          ),
          StageTabs(
            selected: _selected,
            onSelected: (stage) => setState(() => _selected = stage),
            counts: counts,
          ),
          Expanded(
            child: applicants.isEmpty
                ? _Empty(searching: _query.isNotEmpty)
                // 시안: 화면 여백 16dp · 카드 사이 12dp
                : ListView.separated(
                    padding: const EdgeInsets.all(AppSpace.s4),
                    itemCount: applicants.length,
                    separatorBuilder: (_, _) =>
                        const SizedBox(height: AppSpace.s3),
                    itemBuilder: (_, i) => ApplicantCard(
                      applicant: applicants[i],
                      onTap: () => Navigator.pushNamed(
                        context,
                        Routes.applicantDetail,
                        arguments: (applicants[i], widget.posting.title),
                      ),
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}

/// 이 단계에 보여 줄 사람이 없을 때. **문구가 두 가지다** —
/// 그냥 없는 것과 검색으로 걸러져 없는 것은 담당자가 할 일이 다르다
/// (기다린다 / 검색어를 지운다). 문구는 웹 소스 그대로.
class _Empty extends StatelessWidget {
  const _Empty({required this.searching});

  final bool searching;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpace.s5),
        child: Text(
          searching ? '조건에 맞는 지원자가 없습니다.' : '아직 지원자가 없습니다.',
          textAlign: TextAlign.center,
          style: const TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.sm,
            color: AppColors.textSub,
          ),
        ),
      ),
    );
  }
}
