/// 지원자 (지원자 탭) — 앱 UI 초안(2026-09-01) 조각 12.
///
/// 05-design §0.5: "지원자 | **전 공고 통합 검색 테이블** — 10만 건 검색·복합 필터
/// 무대(B 성능 스토리, 응답 시간 표기). **칸반 없음**".
///
/// 공고 하나를 파고들어 보는 [ApplicantsScreen] 과 다르다. 여기는 공고를 가리지
/// 않고 전부 훑는 자리라 카드마다 공고명을 함께 적는다.
///
/// §9 "테이블은 카드형" 대로 테이블을 카드로 편다. 웹의 6열(이름·공고·단계·경력·
/// 평가·지원일)은 375px 에 들어가지 않는다.
///
/// **응답 시간은 아직 적지 않는다.** 목데이터를 로컬에서 거르는 시간은 API 왕복이
/// 아니라 성능 이야기가 되지 못한다 — 지어낸 숫자를 적느니 비워 둔다.
/// API 연동(큐 8) 때 서버가 준 값으로 붙인다.
library;

import 'package:flutter/material.dart';

import 'dart:async';

import '../api/api_error.dart';
import '../auth/authed_client.dart';
import '../data/applicant_repository.dart';
import '../data/posting_repository.dart';
import '../data/repositories.dart';
import '../models/applicant.dart';
import '../models/stage.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';
import '../widgets/applicant_card.dart';

class ApplicantsSearchScreen extends StatefulWidget {
  const ApplicantsSearchScreen({
    super.key,
    this.onOpenApplicant,
    this.repository,
    this.postingRepository,
  });

  final void Function(Applicant applicant, String postingTitle)?
  onOpenApplicant;

  /// 테스트가 가짜를 넣는 자리 (큐 8 4단계)
  final ApplicantRepository? repository;
  final PostingRepository? postingRepository;

  @override
  State<ApplicantsSearchScreen> createState() => _ApplicantsSearchScreenState();
}

class _ApplicantsSearchScreenState extends State<ApplicantsSearchScreen> {
  final _controller = TextEditingController();

  /// null = 전체. 05-design 은 지원자 화면에 칸반을 두지 않으므로 필터는 칩뿐이다
  Stage? _stage;

  late ApplicantRepository _repo;
  late PostingRepository _postings;

  /// 받아 둔 결과. "더 보기" 로 뒤에 이어 붙인다
  List<Applicant> _results = const [];

  /// 서버가 센 전체 건수. 이걸로 "더 보기" 를 보일지 정한다
  int? _total;

  /// `공고 id → 제목`. **검색 결과에 공고명이 없다** — 한 번 받아 표로 둔다
  Map<int, String> _titles = const {};

  bool _loading = true;
  bool _loadingMore = false;
  Object? _error;

  /// 한 번에 받는 수. 웹은 30이다
  static const _pageSize = 30;

  /// 타자마다 요청을 보내지 않는다. 지금까지는 로컬 필터라 공짜였지만
  /// 서버가 되면 **글자 하나에 왕복 하나**가 된다
  Timer? _debounce;
  static const _debounceDelay = Duration(milliseconds: 300);

  @override
  void initState() {
    super.initState();
    _repo =
        widget.repository ??
        RepositoryScope.of(context)?.applicants ??
        ApplicantRepository(authedClient());
    _postings =
        widget.postingRepository ??
        RepositoryScope.of(context)?.postings ??
        PostingRepository(authedClient());
    _loadTitles();
    // 첫 요청은 [_fetch] 로 바로 간다 — [_search] 는 앞에서 setState 를 부르는데
    // initState 에서 setState 를 부르면 터진다
    _fetch();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    super.dispose();
  }

  /// 공고명 표. **못 받아도 목록은 보여 준다** — 공고명이 빈 칸일 뿐이다
  /// (웹 `Evaluations.tsx` 도 같은 처리)
  Future<void> _loadTitles() async {
    try {
      final list = await _postings.list();
      if (!mounted) return;
      setState(() {
        _titles = {for (final p in list) p.posting.id: p.posting.title};
      });
    } on Exception {
      // 그대로 둔다
    }
  }

  void _onQueryChanged() {
    _debounce?.cancel();
    _debounce = Timer(_debounceDelay, _search);
  }

  /// 처음부터 다시 받는다 — 검색어·단계가 바뀌면 앞 페이지도 달라진다
  Future<void> _search() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    await _fetch();
  }

  Future<void> _fetch() async {
    try {
      // 공고명이 걸리면 그 공고로 좁힌다 — 그때 `q` 는 안 보낸다.
      // 둘 다 보내면 서버가 AND 로 묶어 교집합이 되어 아무것도 안 나온다
      final postingId = _matchedPostingId;
      final page = await _repo.search(
        query: postingId == null ? _controller.text.trim() : null,
        stage: _stage,
        postingId: postingId,
        limit: _pageSize,
      );
      if (!mounted) return;
      setState(() {
        _results = page.items;
        _total = page.total;
        _loading = false;
      });
    } on Object catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e;
        _loading = false;
      });
    }
  }

  /// 뒤에 이어 붙인다. 폰이라 페이지 번호 대신 "더 보기" 다 —
  /// `< 1/5 >` 는 엄지로 누르기에도, 어디까지 봤는지 알기에도 안 맞는다
  Future<void> _loadMore() async {
    if (_loadingMore) return;
    setState(() => _loadingMore = true);

    try {
      final postingId = _matchedPostingId;
      final page = await _repo.search(
        query: postingId == null ? _controller.text.trim() : null,
        stage: _stage,
        postingId: postingId,
        limit: _pageSize,
        offset: _results.length,
      );
      if (!mounted) return;
      setState(() {
        _results = [..._results, ...page.items];
        _total = page.total ?? _total;
        _loadingMore = false;
      });
    } on Object {
      if (!mounted) return;
      // 이어 붙이기 실패는 이미 본 목록을 지우지 않는다 — 다시 누르면 된다
      setState(() => _loadingMore = false);
    }
  }

  String _postingTitleOf(Applicant a) => _titles[a.jobPostingId] ?? '';

  /// 검색어가 공고명이면 그 공고 id.
  ///
  /// placeholder 가 "이름 또는 공고 검색" 인데 **서버의 `q` 는 이름·이메일만
  /// 본다**(backend/app/api/search.py:120). 공고는 `posting_id` 로 좁혀야 한다 —
  /// 웹도 같은 이유로 공고 검색을 따로 처리한다(`postingIdFilter`).
  int? get _matchedPostingId {
    final term = _controller.text.trim().toLowerCase();
    if (term.isEmpty) return null;
    for (final e in _titles.entries) {
      if (e.value.toLowerCase().contains(term)) return e.key;
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final results = _results;
    final searching = _controller.text.trim().isNotEmpty;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // 검색·필터는 스크롤과 함께 올라가지 않는다 — 거른 조건이 늘 보여야 한다
        Container(
          color: AppColors.bgElev,
          padding: const EdgeInsets.fromLTRB(
            AppSpace.s4,
            AppSpace.s3,
            AppSpace.s4,
            0,
          ),
          child: Column(
            children: [
              _SearchField(
                controller: _controller,
                // 글자마다 보내지 않는다 — 300ms 쉬면 그때 한 번 보낸다
                onChanged: (_) {
                  setState(() {});
                  _onQueryChanged();
                },
                onClear: () {
                  setState(_controller.clear);
                  _onQueryChanged();
                },
              ),
              _StageChips(
                selected: _stage,
                // 칩은 누르는 즉시다 — 타자와 달리 연달아 눌리지 않는다
                onSelected: (s) {
                  setState(() => _stage = s);
                  _search();
                },
              ),
            ],
          ),
        ),
        const Divider(height: 1, thickness: 1, color: AppColors.border),

        Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpace.s4,
            AppSpace.s3,
            AppSpace.s4,
            AppSpace.s1,
          ),
          child: Text(
            // 서버가 센 전체를 적는다 — 받아 둔 만큼이 아니라(더 보기 전이라도
            // "48명" 이 맞다). 못 세었으면 받아 둔 수로 대신한다
            formatItemCount(_total ?? results.length),
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.caption,
              fontFeatures: AppType.tabularNums,
              color: AppColors.textSub,
            ),
          ),
        ),

        Expanded(child: _list(results, searching)),
      ],
    );
  }

  /// §6 세 상태 + "더 보기".
  ///
  /// 목록을 [AsyncView] 로 감싸지 않는다 — 검색어를 고칠 때마다 화면이 통째로
  /// 로딩으로 바뀌면 방금 본 결과가 사라져 뭘 고치는지 알 수 없다. 로딩은
  /// **처음 한 번만** 전체를 덮고, 그 뒤로는 목록을 두고 위에서 갈린다.
  Widget _list(List<Applicant> results, bool searching) {
    if (_loading && results.isEmpty) {
      return const Center(
        child: Text(
          '불러오는 중…',
          style: TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.sm,
            color: AppColors.textSub,
          ),
        ),
      );
    }

    if (_error != null && results.isEmpty) {
      return _SearchError(error: _error!, onRetry: _search);
    }

    if (results.isEmpty) return _Empty(searching: searching);

    // 받아 둔 것보다 전체가 많으면 마지막에 [더 보기] 한 칸을 더 그린다
    final hasMore = (_total ?? results.length) > results.length;

    return ListView.separated(
      padding: const EdgeInsets.fromLTRB(
        AppSpace.s4,
        AppSpace.s2,
        AppSpace.s4,
        AppSpace.s4,
      ),
      itemCount: results.length + (hasMore ? 1 : 0),
      separatorBuilder: (_, _) => const SizedBox(height: AppSpace.s3),
      itemBuilder: (_, i) {
        if (i == results.length) {
          return _MoreButton(busy: _loadingMore, onTap: _loadMore);
        }
        final applicant = results[i];
        final title = _postingTitleOf(applicant);
        return ApplicantCard(
          applicant: applicant,
          postingTitle: title,
          onTap: widget.onOpenApplicant == null
              ? null
              : () => widget.onOpenApplicant!(applicant, title),
        );
      },
    );
  }
}

/// 검색 실패 — §6. 앱에는 F5 가 없어 [다시 시도] 를 단다.
class _SearchError extends StatelessWidget {
  const _SearchError({required this.error, required this.onRetry});

  final Object error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpace.s6),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              // 서버가 준 문구가 있으면 그대로 — 왜 안 됐는지가 거기 있다
              error is ApiError
                  ? (error as ApiError).message
                  : '지원자를 불러오지 못했습니다',
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.sm,
                height: 1.5,
                color: AppColors.textSub,
              ),
            ),
            const SizedBox(height: AppSpace.s4),
            SizedBox(
              height: AppLayout.minTouchTarget,
              child: OutlinedButton(
                onPressed: onRetry,
                child: const Text('다시 시도'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// 다음 쪽 — 폰이라 페이지 번호 대신 이어 붙인다.
class _MoreButton extends StatelessWidget {
  const _MoreButton({required this.busy, required this.onTap});

  final bool busy;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: AppLayout.minTouchTarget,
      child: OutlinedButton(
        onPressed: busy ? null : onTap,
        child: busy
            ? const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: AppColors.textSub,
                ),
              )
            : const Text('더 보기'),
      ),
    );
  }
}

/// 검색 칸 — 05-design §4 인풋은 `--bg-sunken` 바탕(패널보다 한 단계 아래).
class _SearchField extends StatelessWidget {
  const _SearchField({
    required this.controller,
    required this.onChanged,
    required this.onClear,
  });

  final TextEditingController controller;
  final ValueChanged<String> onChanged;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      onChanged: onChanged,
      style: const TextStyle(
        fontFamily: AppType.fontFamily,
        fontSize: AppType.body,
        color: AppColors.text,
      ),
      decoration: InputDecoration(
        isDense: true,
        filled: true,
        fillColor: AppColors.bgSunken,
        // 웹과 같은 문구
        hintText: '이름 또는 공고 검색',
        hintStyle: const TextStyle(
          fontFamily: AppType.fontFamily,
          fontSize: AppType.body,
          color: AppColors.textSub,
        ),
        prefixIcon: const Icon(
          Icons.search,
          size: 20,
          color: AppColors.textSub,
        ),
        suffixIcon: controller.text.isEmpty
            ? null
            : IconButton(
                icon: const Icon(Icons.close, size: 20),
                color: AppColors.textSub,
                tooltip: '검색어 지우기',
                onPressed: onClear,
              ),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: AppSpace.s3,
          vertical: AppSpace.s3,
        ),
        border: const OutlineInputBorder(
          borderRadius: AppShape.ctl,
          borderSide: BorderSide(
            color: AppColors.border,
            width: AppShape.borderW,
          ),
        ),
        enabledBorder: const OutlineInputBorder(
          borderRadius: AppShape.ctl,
          borderSide: BorderSide(
            color: AppColors.border,
            width: AppShape.borderW,
          ),
        ),
        focusedBorder: const OutlineInputBorder(
          borderRadius: AppShape.ctl,
          borderSide: BorderSide(
            color: AppColors.leaf,
            width: AppShape.borderW,
          ),
        ),
      ),
    );
  }
}

/// 단계 필터 칩 — 전체 + 5 단계. 가로로 넘치면 스크롤한다.
///
/// 05-design §9 "칸반 대신 단계 탭 + 리스트". 여기는 전 공고 통합이라 단계별
/// 인원을 세어 붙이지 않는다 — 공고가 섞이면 그 숫자가 무엇의 합인지 애매해진다.
class _StageChips extends StatelessWidget {
  const _StageChips({required this.selected, required this.onSelected});

  final Stage? selected;
  final ValueChanged<Stage?> onSelected;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 58,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(vertical: AppSpace.s3),
        children: [
          _Chip(
            label: '전체',
            selected: selected == null,
            onTap: () => onSelected(null),
          ),
          for (final stage in Stage.values) ...[
            const SizedBox(width: AppSpace.s2),
            _Chip(
              label: stage.label,
              selected: selected == stage,
              onTap: () => onSelected(stage),
            ),
          ],
        ],
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: selected,
      child: Material(
        color: selected ? AppColors.sproutSoft : AppColors.bgSunken,
        borderRadius: AppShape.pill,
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          highlightColor: AppColors.sunkenHover,
          splashColor: AppColors.sunkenHover,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: AppSpace.s4),
            alignment: Alignment.center,
            decoration: BoxDecoration(
              borderRadius: AppShape.pill,
              border: Border.all(
                color: selected ? AppColors.sprout : AppColors.border,
                width: AppShape.borderW,
              ),
            ),
            child: Text(
              label,
              softWrap: false,
              style: TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.sm,
                // 사이드바와 같은 규칙 — 강조는 배경과 색으로만, 굵기는 안 건드린다
                fontWeight: selected ? AppType.wSemiBold : AppType.wRegular,
                color: selected ? AppColors.leaf : AppColors.textSub,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// 빈 상태 — 05-design §6. 문구는 웹(`Applicants.tsx`)에서 그대로 가져왔다.
class _Empty extends StatelessWidget {
  const _Empty({required this.searching});

  final bool searching;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpace.s6),
        child: Text(
          searching ? '검색 결과가 없습니다.' : '등록된 지원자가 없습니다.',
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
