import 'package:flutter/material.dart';

import '../auth/authed_client.dart';
import '../data/applicant_repository.dart';
import '../data/repositories.dart';
import '../models/applicant.dart';
import '../models/job_posting.dart';
import '../models/stage.dart';
import '../routes.dart';
import '../theme/tokens.dart';
import '../widgets/app_top_bar.dart';
import '../widgets/async_view.dart';
import '../widgets/applicant_card.dart';
import '../widgets/posting_header.dart';
import '../widgets/search_field.dart';
import '../widgets/stage_tabs.dart';
// 공고 수정 화면이 돌려주는 삭제 표시([PostingDeleted]) 하나 때문에 부른다 —
// 화면끼리는 경로 이름으로만 오가지만, 돌아오는 값의 타입은 만든 쪽에 있다
import 'posting_form_screen.dart';

/// 한 공고의 지원자 리스트. 공고 리스트에서 공고를 골라 들어온다.
///
/// 화면 구성은 시안(2026-08-28) 4번 + 검색(2026-09-02 추가):
/// 상단 바 → 공고명·마감·총원 → 퍼널 막대 → **검색** → 단계 탭 → 카드 리스트.
///
/// **서버에서 받아 온다**(큐 8, 2026-09-02). 목록 API 는 이름·이메일·단계·
/// 경력·지원일만 주므로 **카드에 학력·기술이 없다** — 그것들은 상세에만 있다.
class ApplicantsScreen extends StatefulWidget {
  const ApplicantsScreen({super.key, required this.posting, this.repository});

  final JobPosting posting;

  /// 테스트가 가짜를 넣는 자리
  final ApplicantRepository? repository;

  @override
  State<ApplicantsScreen> createState() => _ApplicantsScreenState();
}

class _ApplicantsScreenState extends State<ApplicantsScreen> {
  /// **null = 전체.** 웹은 공고를 열면 전 단계를 한 표에 보여 준다(2026-09-02).
  /// 지원 접수만 먼저 띄우면 다른 단계에 사람이 있는지 알려면 탭을 눌러 봐야 한다
  Stage? _selected;

  final _search = TextEditingController();
  String _query = '';

  /// 웹과 같은 기본값 — 이름·이메일을 다 뒤진다
  SearchScope _scope = SearchScope.all;

  late ApplicantRepository _repo;
  late Future<List<Applicant>> _future;

  /// 받아 온 목록. 단계 탭·검색이 이걸 거른다 — 탭을 옮길 때마다 다시 부르지
  /// 않는다(한 공고에 수십 명이라 한 번 받아 거르는 쪽이 왕복이 적다)
  List<Applicant> _all = const [];

  /// 지금 보고 있는 공고. 수정하고 돌아오면 여기가 바뀐다 —
  /// `widget.posting` 만 보면 고친 제목·마감일이 헤더에 안 나타난다
  late JobPosting _posting = widget.posting;

  /// 공고를 고쳤는가. 뒤로 갈 때 목록에게 알려 준다 —
  /// 목록이 그대로면 고친 것이 반영 안 된 줄 안다
  bool _postingChanged = false;

  /// 공고 수정 — 상단 바의 [✎] (2026-09-03).
  Future<void> _editPosting() async {
    final result = await Navigator.pushNamed(
      context,
      Routes.postingEdit,
      arguments: _posting,
    );
    if (!mounted) return;

    // 지웠으면 이 화면도 닫는다 — 없어진 공고의 지원자 목록이다. 목록에는
    // `true` 로 알려 다시 받게 한다: 그대로 두면 사라진 공고 카드가 남는다
    if (result is PostingDeleted) {
      Navigator.pop(context, true);
      return;
    }

    if (result is! JobPosting) return;

    setState(() {
      _posting = result;
      _postingChanged = true;
    });
  }

  @override
  void initState() {
    super.initState();
    _repo =
        widget.repository ??
        RepositoryScope.of(context)?.applicants ??
        ApplicantRepository(authedClient());
    _future = _load();
  }

  /// `ignore()` 이유는 postings_screen.dart 참고 — FutureBuilder 가 붙기 전에
  /// 실패하면 듣는 사람이 없는 오류가 된다
  Future<List<Applicant>> _load() =>
      _repo.byPosting(widget.posting.id).then((list) {
        _all = list;
        return list;
      })..ignore();

  void _reload() {
    setState(() {
      _future = _load();
    });
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  /// 단계별 인원 — 퍼널 바와 탭이 함께 쓴다.
  /// **검색과 무관하게 전체를 센다** — 걸러진 수를 탭에 달면 검색어를 지우기
  /// 전까지 이 공고에 몇 명이 있는지 알 수 없다.
  Map<Stage, int> get _counts => {
    for (final s in Stage.values)
      s: _all.where((a) => a.currentStage == s).length,
  };

  /// role/app.md §3: 단계 탭은 **필터**다. 고른 단계만 보여 주고, 전체면 다 본다.
  /// 검색어가 있으면 그 안에서 [_scope] 대로 한 번 더 거른다.
  List<Applicant> get _visible {
    final stage = _selected == null
        ? _all
        : _all.where((a) => a.currentStage == _selected).toList();
    if (_query.isEmpty) return stage;

    final q = _query.toLowerCase();
    return stage.where((a) => _matches(a, q)).toList();
  }

  bool _matches(Applicant a, String q) => switch (_scope) {
    SearchScope.name => a.name.toLowerCase().contains(q),
    SearchScope.email => a.email.toLowerCase().contains(q),
    SearchScope.all =>
      a.name.toLowerCase().contains(q) || a.email.toLowerCase().contains(q),
  };

  @override
  Widget build(BuildContext context) {
    // 뒤로 갈 때 "공고가 바뀌었다" 를 들려 보낸다. 기기 뒤로가기(제스처·버튼)도
    // 상단 바 [←] 와 같은 값을 내야 해서 PopScope 로 한 번 더 막는다
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) Navigator.pop(context, _postingChanged);
      },
      child: _scaffold(),
    );
  }

  Widget _scaffold() {
    return Scaffold(
      appBar: AppTopBar(
        title: '지원자',
        showBack: true,
        onBackPressed: () => Navigator.pop(context, _postingChanged),
        onEditPressed: _editPosting,
      ),
      // 빈 상태를 AsyncView 에 맡기지 않는다 — 지원자가 없어도 공고 머리와
      // 단계 탭은 남아야 "이 공고에 아무도 없다" 가 읽힌다
      body: AsyncView<List<Applicant>>(
        future: _future,
        onRetry: _reload,
        emptyMessage: '',
        // **목록을 여기 안에서 센다.** 바깥 build 에서 미리 계산하면 로딩
        // 시점의 빈 값이 굳는다 — FutureBuilder 는 이 builder 만 다시 부르지
        // State.build 를 다시 부르지 않는다
        builder: (context, _) => _body(_visible, _counts),
      ),
    );
  }

  Widget _body(List<Applicant> applicants, Map<Stage, int> counts) {
    return Column(
      children: [
        PostingHeader(posting: _posting, counts: counts),
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
            // 웹과 같은 문구
            hintText: '검색어 입력',
            scope: _scope,
            onScopeChanged: (s) => setState(() => _scope = s),
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
              ? _Empty(searching: _query.isNotEmpty, noneAtAll: _all.isEmpty)
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
                      arguments: (applicants[i], _posting.title),
                    ),
                  ),
                ),
        ),
      ],
    );
  }
}

/// 보여 줄 사람이 없을 때. **문구가 세 가지다** — 담당자가 할 일이 다르다.
///
/// - 검색 중 → 검색어를 지운다
/// - 이 공고에 아무도 없다 → 기다린다
/// - 이 단계만 비었다 → 다른 탭을 본다 (전체 탭에서는 나오지 않는다)
///
/// 셋을 한 문구로 묶으면 "지원자가 없습니다" 를 보고 공고 전체가 빈 줄 안다.
/// 앞 둘의 문구는 웹 소스 그대로다.
class _Empty extends StatelessWidget {
  const _Empty({required this.searching, required this.noneAtAll});

  final bool searching;
  final bool noneAtAll;

  @override
  Widget build(BuildContext context) {
    final message = switch ((searching, noneAtAll)) {
      (true, _) => '조건에 맞는 지원자가 없습니다.',
      (false, true) => '아직 지원자가 없습니다.',
      (false, false) => '이 단계에 지원자가 없습니다.',
    };

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpace.s5),
        child: Text(
          message,
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
