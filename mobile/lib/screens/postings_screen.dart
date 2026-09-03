import 'package:flutter/material.dart';

import '../auth/authed_client.dart';
import '../data/posting_repository.dart';
import '../data/repositories.dart';
import '../models/job_posting.dart';
import '../routes.dart';
import '../theme/tokens.dart';
import '../widgets/async_view.dart';
import '../widgets/posting_card.dart';

/// 채용 공고 목록 — 시안(2026-08-28) 5번.
///
/// 웹은 `공고 → 그 공고의 지원자` 순이고(05-design §0.5 화면 지도),
/// 앱이 지원자에서 시작하면 지금 어느 공고를 보는 중인지가 화면에 없다.
///
/// **본문만 그린다.** 상단 바·하단 탭바는 [HomeShell] 이 준다(조각 2) —
/// 탭을 옮겨도 껍데기는 그대로 있고 이 자리만 바뀌어야 하기 때문이다.
///
/// **서버에서 받아 온다**(큐 8, 2026-09-02). 목데이터를 걷어낸 첫 화면이다.
class PostingsScreen extends StatefulWidget {
  const PostingsScreen({super.key, this.repository, this.reloadSignal});

  /// 테스트가 가짜를 넣는 자리
  final PostingRepository? repository;

  /// 바깥에서 "다시 받아라" 고 알리는 자리. [HomeShell] 의 `[+]` 가 공고를
  /// 만들고 돌아오면 흔든다 — 목록이 그대로면 방금 만든 공고가 안 보인다.
  ///
  /// `[+]` 는 상단 바(HomeShell)에 있고 목록은 여기 있어서 서로 닿지 않는다
  final Listenable? reloadSignal;

  @override
  State<PostingsScreen> createState() => _PostingsScreenState();
}

class _PostingsScreenState extends State<PostingsScreen> {
  late PostingRepository _repo;
  late Future<List<PostingWithCounts>> _future;

  @override
  void initState() {
    super.initState();
    _repo =
        widget.repository ??
        RepositoryScope.of(context)?.postings ??
        PostingRepository(authedClient());
    _future = _load();
    widget.reloadSignal?.addListener(_reload);
  }

  @override
  void dispose() {
    widget.reloadSignal?.removeListener(_reload);
    super.dispose();
  }

  /// 요청을 시작한다.
  ///
  /// `ignore()` 를 붙이는 이유: 요청이 **[FutureBuilder] 가 붙기 전에** 실패하면
  /// (연결 즉시 거부·이미 끊긴 상태) 듣는 사람이 없는 오류가 되어 Dart 가
  /// "잡히지 않은 예외" 로 앱을 흔든다. 화면은 어차피 오류 상태로 그린다 —
  /// 여기서 미리 한 번 들어 두고, 표시는 FutureBuilder 가 따로 한다.
  Future<List<PostingWithCounts>> _load() => _repo.list()..ignore();

  /// [다시 시도] — **새 Future 를 만든다.** 실패한 Future 를 다시 기다려 봐야
  /// 같은 실패가 나온다.
  ///
  /// 화살표로 쓰면(`setState(() => _future = ...)`) 대입식의 값인 Future 가
  /// 콜백의 반환값이 되어 Flutter 가 "setState 안에서 비동기 작업" 으로 보고
  /// 막는다. 블록으로 둬서 반환값을 없앤다
  void _reload() {
    setState(() {
      _future = _load();
    });
  }

  /// 공고 → 그 공고의 지원자. 거기서 공고를 고치고 나오면 `true` 가 돌아온다 —
  /// 그때만 다시 받는다. 제목·마감일이 여기 카드에도 걸려 있어서 그대로 두면
  /// 방금 고친 것이 안 반영된 줄 안다 (2026-09-03)
  Future<void> _openApplicants(JobPosting posting) async {
    final changed = await Navigator.pushNamed(
      context,
      Routes.applicants,
      arguments: posting,
    );
    if (changed == true && mounted) _reload();
  }

  @override
  Widget build(BuildContext context) {
    return AsyncView<List<PostingWithCounts>>(
      future: _future,
      onRetry: _reload,
      // 웹과 같은 문구
      emptyMessage: '등록된 공고가 없습니다.',
      isEmpty: (list) => list.isEmpty,
      builder: (context, items) => RefreshIndicator(
        // 폰에서 새로 고치는 관습은 당겨서다. [다시 시도] 는 오류일 때만 나온다
        onRefresh: () async {
          final next = _load();
          setState(() {
            _future = next;
          });
          // 스피너를 언제 거둘지 RefreshIndicator 가 알아야 한다
          await next;
        },
        color: AppColors.leaf,
        child: ListView.separated(
          // 시안: 화면 여백 16dp · 카드 사이 12dp
          padding: const EdgeInsets.all(AppSpace.s4),
          itemCount: items.length,
          separatorBuilder: (_, _) => const SizedBox(height: AppSpace.s3),
          itemBuilder: (_, i) => PostingCard(
            posting: items[i].posting,
            counts: items[i].counts,
            onTap: () => _openApplicants(items[i].posting),
          ),
        ),
      ),
    );
  }
}
