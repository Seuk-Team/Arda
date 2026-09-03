import 'package:flutter/material.dart';

import '../api/api_error.dart';
import '../auth/authed_client.dart';
import '../auth/current_user.dart';
import '../data/applicant_repository.dart';
import '../data/repositories.dart';
import '../models/applicant.dart';
import '../models/evaluation.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';
import '../widgets/app_top_bar.dart';
import '../widgets/async_view.dart';

/// 평가 목록 — 시안(2026-08-28) 3번.
///
/// 웹에는 있는데 폰에서 놓을 자리가 없던 것이다. 상세 화면 안의 한 섹션이 아니라
/// **별도 화면**으로 뺐다 — 코멘트가 길어 상세에 끼우면 지원 정보가 아래로 밀린다.
///
/// **평균을 먼저, 개별을 다음에.** 스크롤 없이 보이는 첫 화면에 판단에 쓰는
/// 값(평균·인원)을 놓고, 근거인 코멘트는 그 아래로 둔다.
///
/// 치수(시안): 평균 블록 여백 16dp · 평가 항목 최소 72dp
///
/// **서버에서 받아 오고 쓸 수도 있다** (큐 8 3단계, 2026-09-03).
class EvaluationsScreen extends StatefulWidget {
  const EvaluationsScreen({
    super.key,
    required this.applicant,
    this.repository,
  });

  final Applicant applicant;

  /// 테스트가 가짜를 넣는 자리
  final ApplicantRepository? repository;

  @override
  State<EvaluationsScreen> createState() => _EvaluationsScreenState();
}

class _EvaluationsScreenState extends State<EvaluationsScreen> {
  late ApplicantRepository _repo;
  late Future<EvaluationSummary> _future;

  @override
  void initState() {
    super.initState();
    _repo =
        widget.repository ??
        RepositoryScope.of(context)?.applicants ??
        ApplicantRepository(authedClient());
    _future = _load();
  }

  /// `ignore()` 이유는 postings_screen.dart 참고
  Future<EvaluationSummary> _load() =>
      _repo.evaluations(widget.applicant.id)..ignore();

  void _reload() {
    setState(() {
      _future = _load();
    });
  }

  @override
  Widget build(BuildContext context) {
    // 내가 쓴 평가를 찾으려면 내 id 가 필요하다. 로그인 전이면 null 이고,
    // 그때는 늘 "새로 쓰기" 로 둔다 — 남의 평가를 내 것으로 열면 안 된다
    final me = CurrentUserScope.of(context);

    return Scaffold(
      appBar: const AppTopBar(title: '평가', showBack: true),
      body: AsyncView<EvaluationSummary>(
        future: _future,
        onRetry: _reload,
        // 평가가 없어도 평균 블록과 입력칸은 남아야 한다 — 여기가 쓰는 화면이다
        emptyMessage: '',
        builder: (context, summary) => _body(summary, me?.id),
      ),
    );
  }

  Widget _body(EvaluationSummary summary, int? myId) {
    // 내가 쓴 것. 있으면 새로 만들지 않고 그걸 고친다 — 서버도 웹도 중복을
    // 막지 않아 그냥 쓰면 한 사람이 여러 줄을 남기고 평균이 틀어진다
    final mine = myId == null
        ? null
        : summary.items.where((e) => e.evaluatorId == myId).firstOrNull;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _Average(summary: summary),
        Expanded(
          child: ListView(
            padding: const EdgeInsets.all(AppSpace.s4),
            children: [
              _MyEvaluation(
                existing: mine,
                onSubmit: (score, comment) async {
                  if (mine == null) {
                    await _repo.addEvaluation(
                      widget.applicant.id,
                      score: score,
                      comment: comment,
                    );
                  } else {
                    await _repo.updateEvaluation(
                      mine.id,
                      score: score,
                      comment: comment,
                    );
                  }
                  // 평균과 인원이 함께 맞아야 해서 목록째 다시 받는다
                  _reload();
                },
              ),
              for (final item in summary.items) ...[
                const Divider(height: AppSpace.s5),
                _EvaluationItem(item: item, isMine: item.id == mine?.id),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

/// 내 평가 — 이 화면에서 유일하게 **쓰는** 자리.
///
/// 이미 쓴 것이 있으면 새로 만들지 않고 그걸 고친다(2026-09-03 결정).
/// 서버에 `PATCH /evaluations/{id}` 가 "내 것만 고칠 수 있다" 는 검사까지
/// 갖춰져 있는데 웹이 안 쓰고 있었다 — 앱이 먼저 쓴다.
class _MyEvaluation extends StatefulWidget {
  const _MyEvaluation({required this.existing, required this.onSubmit});

  /// 내가 이미 쓴 평가. 없으면 새로 쓴다
  final Evaluation? existing;

  final Future<void> Function(int score, String? comment) onSubmit;

  @override
  State<_MyEvaluation> createState() => _MyEvaluationState();
}

class _MyEvaluationState extends State<_MyEvaluation> {
  final _comment = TextEditingController();
  int? _score;
  bool _sending = false;

  bool get _editing => widget.existing != null;

  @override
  void initState() {
    super.initState();
    _fill();
  }

  @override
  void didUpdateWidget(_MyEvaluation old) {
    super.didUpdateWidget(old);
    // 저장하고 목록을 다시 받으면 내 평가가 새 값으로 들어온다.
    // 다른 평가로 바뀐 것이 아니면 입력칸을 건드리지 않는다 — 고치는 중에
    // 글자가 사라지면 안 된다
    if (widget.existing?.id != old.existing?.id) _fill();
  }

  void _fill() {
    final e = widget.existing;
    _score = e?.score;
    _comment.text = e?.comment ?? '';
  }

  @override
  void dispose() {
    _comment.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final score = _score;
    if (score == null) return;

    final messenger = ScaffoldMessenger.of(context);
    setState(() => _sending = true);

    try {
      // 빈 코멘트는 null 로 보낸다 — 웹과 같다
      final text = _comment.text.trim();
      await widget.onSubmit(score, text.isEmpty ? null : text);
      if (!mounted) return;

      messenger.showSnackBar(
        SnackBar(
          // 어미까지 통째로 고른다 — 앞부분만 갈아 끼우면 "수정습니다" 가 된다
          content: Text('$score점 — 평가를 ${_editing ? '수정했습니다' : '남겼습니다'}'),
        ),
      );
    } on ApiError catch (e) {
      if (!mounted) return;
      // 403 이면 "본인에게 배정된 지원자만 평가할 수 있습니다" 가 온다.
      // 서버 문구를 그대로 쓴다 — 왜 못 쓰는지가 거기 적혀 있다
      messenger.showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          _editing ? '내 평가 수정' : '내 평가',
          style: const TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.sm,
            fontWeight: AppType.wSemiBold,
            color: AppColors.text,
          ),
        ),
        const SizedBox(height: AppSpace.s3),

        // 점수 1~5 — 웹과 같은 다섯 버튼. 드롭다운으로 접으면 한 번 더 눌러야
        // 하고, 폰에서 가장 자주 하는 동작이 이것이다
        Row(
          children: [
            for (var n = 1; n <= 5; n++) ...[
              if (n > 1) const SizedBox(width: AppSpace.s2),
              Expanded(
                child: _ScoreButton(
                  score: n,
                  selected: _score == n,
                  onTap: _sending ? null : () => setState(() => _score = n),
                ),
              ),
            ],
          ],
        ),
        const SizedBox(height: AppSpace.s3),

        TextField(
          controller: _comment,
          minLines: 2,
          maxLines: 5,
          enabled: !_sending,
          style: const TextStyle(
            fontFamily: AppType.fontFamily,
            fontSize: AppType.body,
            color: AppColors.text,
          ),
          decoration: _commentDecoration(),
        ),
        const SizedBox(height: AppSpace.s3),

        SizedBox(
          height: AppLayout.minTouchTarget,
          child: FilledButton(
            // 점수가 없으면 못 보낸다 — 서버도 422 로 막는다
            onPressed: _score == null || _sending ? null : _submit,
            child: _sending
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: AppColors.bgElev,
                    ),
                  )
                : Text(_editing ? '수정' : '저장'),
          ),
        ),
      ],
    );
  }
}

/// 점수 한 칸 — 고른 것만 잎초록 (§1 색은 판단에만).
class _ScoreButton extends StatelessWidget {
  const _ScoreButton({
    required this.score,
    required this.selected,
    required this.onTap,
  });

  final int score;
  final bool selected;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: selected,
      label: '$score점',
      onTap: onTap,
      // 안쪽 숫자의 의미를 지운다 — 안 그러면 "4점" 다음에 "4" 를 또 읽는다
      excludeSemantics: true,
      child: Material(
        color: selected ? AppColors.sproutSoft : AppColors.bgSunken,
        shape: RoundedRectangleBorder(
          borderRadius: AppShape.ctl,
          side: BorderSide(
            color: selected ? AppColors.sprout : AppColors.border,
            width: AppShape.borderW,
          ),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          highlightColor: AppColors.sunkenHover,
          splashColor: AppColors.sunkenHover,
          child: Container(
            height: AppLayout.minTouchTarget,
            alignment: Alignment.center,
            child: Text(
              '$score',
              style: TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.body,
                fontWeight: selected ? AppType.wSemiBold : AppType.wRegular,
                fontFeatures: AppType.tabularNums,
                color: selected ? AppColors.leaf : AppColors.textSub,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// 05-design §4: 인풋은 sunken 바탕.
InputDecoration _commentDecoration() {
  const outline = OutlineInputBorder(
    borderRadius: AppShape.ctl,
    borderSide: BorderSide(color: AppColors.border, width: AppShape.borderW),
  );

  return const InputDecoration(
    isDense: true,
    filled: true,
    fillColor: AppColors.bgSunken,
    hintText: '코멘트 (선택)',
    hintStyle: TextStyle(
      fontFamily: AppType.fontFamily,
      fontSize: AppType.body,
      color: AppColors.textSub,
    ),
    contentPadding: EdgeInsets.all(AppSpace.s3),
    border: outline,
    enabledBorder: outline,
    focusedBorder: OutlineInputBorder(
      borderRadius: AppShape.ctl,
      borderSide: BorderSide(color: AppColors.leaf, width: AppShape.borderW),
    ),
  );
}

/// 평균 + 점수 분포 — 시안: 평균 4.3이 "4·4·5"인지 "3·5·5"인지는 다른 이야기다.
class _Average extends StatelessWidget {
  const _Average({required this.summary});

  final EvaluationSummary summary;

  @override
  Widget build(BuildContext context) {
    final avg = summary.avgScore;

    return Container(
      padding: const EdgeInsets.all(AppSpace.s4),
      decoration: const BoxDecoration(
        color: AppColors.bgElev,
        border: Border(
          bottom: BorderSide(color: AppColors.border, width: AppShape.borderW),
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.baseline,
                textBaseline: TextBaseline.alphabetic,
                children: [
                  Text(
                    avg?.toStringAsFixed(1) ?? '—',
                    // 시안은 40dp 를 제안했으나 05-design §2 스케일(26 이하)에
                    // 없는 값이라 display 로 뒀다. 40 을 쓰려면 토큰 추가가
                    // 필요하다(§0-1, 팀장 승인) — 시안도 "확인 필요"로 표시했다
                    style: const TextStyle(
                      fontFamily: AppType.fontFamily,
                      fontSize: AppType.display,
                      fontWeight: FontWeight.w700,
                      color: AppColors.text,
                      shadows: AppTextShadow.heading,
                      fontFeatures: AppType.tabularNums,
                    ),
                  ),
                  const Text(
                    ' / 5',
                    style: TextStyle(
                      fontFamily: AppType.fontFamily,
                      fontSize: AppType.sm,
                      color: AppColors.textSub,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: AppSpace.s1),
              Text(
                summary.count == 0
                    ? '아직 평가가 없습니다'
                    : '${formatCount(summary.count)}이 평가했습니다',
                softWrap: false,
                style: const TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.sm,
                  color: AppColors.textSub,
                ),
              ),
            ],
          ),

          if (summary.count > 0) ...[
            const SizedBox(width: AppSpace.s5),
            Expanded(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  for (final entry in summary.distribution.entries)
                    if (entry.key >= 3)
                      _DistributionRow(
                        score: entry.key,
                        count: entry.value,
                        total: summary.count,
                      ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// 점수 한 줄 — 시안: 막대 옆에 숫자를 같이 적어 색·길이를 못 읽어도 값이 전달된다.
class _DistributionRow extends StatelessWidget {
  const _DistributionRow({
    required this.score,
    required this.count,
    required this.total,
  });

  final int score;
  final int count;
  final int total;

  @override
  Widget build(BuildContext context) {
    const numberStyle = TextStyle(
      fontFamily: AppType.fontFamily,
      fontSize: AppType.caption,
      color: AppColors.textSub,
      fontFeatures: AppType.tabularNums,
    );

    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpace.s1),
      child: Row(
        children: [
          Text('$score', style: numberStyle),
          const SizedBox(width: AppSpace.s2),
          Expanded(
            child: ClipRRect(
              borderRadius: AppShape.pill,
              child: SizedBox(
                height: 4,
                child: Row(
                  // ColoredBox 는 느슨한 제약에서 높이 0 을 고른다 — 퍼널 바와 같은 함정
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (count > 0)
                      Expanded(
                        flex: count,
                        // 05-design §1: **점수에 색을 쓰지 않는다.**
                        // 평가 점수는 아직 판단이 아니라 재료다
                        child: const DecoratedBox(
                          decoration: BoxDecoration(color: AppColors.neutral),
                        ),
                      ),
                    if (total - count > 0)
                      Expanded(
                        flex: total - count,
                        child: const DecoratedBox(
                          decoration: BoxDecoration(color: AppColors.bgSunken),
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(width: AppSpace.s2),
          Text('$count', style: numberStyle),
        ],
      ),
    );
  }
}

/// 평가 한 건 — 시안: 항목 최소 72dp.
class _EvaluationItem extends StatelessWidget {
  const _EvaluationItem({required this.item, this.isMine = false});

  final Evaluation item;

  /// 내가 쓴 것. 서버가 이름을 안 주므로 **화면에 붙는 유일한 이름**이다 —
  /// 위 입력칸에 뜬 것이 이 줄이라는 것도 이걸로 이어진다
  final bool isMine;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(minHeight: 72),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              // 이름을 못 받으면 점수만 남는다 — 서버는 `evaluator_id` 만 주고
              // "평가자 7번" 은 아무 의미가 없다 (2026-09-02 실측).
              // 내 것만은 누구인지 아니까 "나" 로 적는다
              if (item.evaluatorName != null || isMine) ...[
                Text(
                  isMine ? '나' : item.evaluatorName!,
                  softWrap: false,
                  style: const TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.body,
                    fontWeight: AppType.wSemiBold,
                    color: AppColors.text,
                  ),
                ),
                const SizedBox(width: AppSpace.s2),
                // §1: 점수에 색을 쓰지 않는다
                const Icon(Icons.circle, size: 6, color: AppColors.neutral),
                const SizedBox(width: AppSpace.s1),
              ],
              Text(
                '${item.score}',
                style: const TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.num,
                  fontWeight: AppType.wSemiBold,
                  color: AppColors.text,
                  fontFeatures: AppType.tabularNums,
                ),
              ),
              const Spacer(),
              Text(
                formatDate(item.createdAt),
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
          if (item.comment != null && item.comment!.isNotEmpty) ...[
            const SizedBox(height: AppSpace.s2),
            Text(
              item.comment!,
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.sm,
                color: AppColors.text,
                height: 1.5,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
