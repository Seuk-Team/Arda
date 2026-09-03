import 'package:flutter/material.dart';

import '../auth/authed_client.dart';
import '../data/applicant_repository.dart';
import '../api/api_error.dart';
import '../data/repositories.dart';
import '../models/applicant.dart';
import '../routes.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';
import 'ar_screen.dart';
import '../widgets/async_view.dart';
import '../widgets/detail_blocks.dart';
import '../widgets/detail_section.dart';
import '../widgets/stage_change_sheet.dart';
import '../widgets/stage_label.dart';
import '../widgets/stage_rail.dart';

/// 지원자 상세 — `mockup-mobile.html` 의 `.dpanel` 을 옮긴 것.
///
/// 목업은 한 페이지 안의 전체 화면 오버레이(`transform:translateX`)로 만들었지만,
/// 앱에서는 별도 화면으로 밀어 올린다. Navigator 가 같은 슬라이드 전환을 주므로
/// 보이는 결과는 같고, 뒤로가기·상태 관리는 플랫폼이 맡는다.
///
/// 시안 2·3번이 단계 이력·평가를 별도 화면으로 뺐고, 앱 UI 초안(2026-09-01)이
/// 그중 단계 이력의 **최근 두 건만** 상세로 되살렸다. 전체는 여전히 별도 화면이다.
///
/// **서버에서 받아 온다**(큐 8, 2026-09-02). 목록에서 넘어온 [applicant] 은
/// 이름·단계 정도만 들고 있어서 화면을 열면서 상세를 다시 받는다 —
/// 그 사이 머리(이름·단계)는 넘어온 값으로 미리 그려 빈 화면을 안 보여 준다.
///
/// 평가자·단계 변경자 **이름은 서버가 주지 않는다**(id 뿐). 이름 없이 그리고,
/// 백엔드가 넣어 주면 그때 보인다 — 자세한 것은 각 모델의 `fromJson` 주석.
class ApplicantDetailScreen extends StatefulWidget {
  const ApplicantDetailScreen({
    super.key,
    required this.applicant,
    required this.postingTitle,
    this.repository,
  });

  /// 목록에서 넘어온 것. 상세를 받기 전까지 머리에 쓴다
  final Applicant applicant;

  /// 단계 이력 화면의 부제에 쓴다 — "김도현 · 백엔드 개발자 (신입)"
  final String postingTitle;

  /// 테스트가 가짜를 넣는 자리
  final ApplicantRepository? repository;

  @override
  State<ApplicantDetailScreen> createState() => _ApplicantDetailScreenState();
}

class _ApplicantDetailScreenState extends State<ApplicantDetailScreen> {
  late ApplicantRepository _repo;
  late Future<ApplicantDetail> _future;

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
  Future<ApplicantDetail> _load() =>
      _repo.detail(widget.applicant.id)..ignore();

  void _reload() {
    setState(() {
      _future = _load();
    });
  }

  /// 초안의 `평점 4.3 / 5.0 · 3명`. 평가가 없으면 줄을 만들지 않는다 —
  /// "0.0" 은 나쁜 평가를 받은 것처럼 읽힌다 (D1 지시서)
  String? _ratingLabel(ApplicantDetail d) {
    final avg = d.avgScore;
    if (avg == null) return null;
    return '$avg / 5.0 · ${formatCount(d.evaluations.length)}';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // 머리는 목록에서 넘어온 값으로 바로 그린다 — 이름이 늦게 뜨면
          // 어느 사람을 연 것인지 잠깐 알 수 없다
          _Header(applicant: widget.applicant),
          Expanded(
            child: AsyncView<ApplicantDetail>(
              future: _future,
              onRetry: _reload,
              emptyMessage: '',
              builder: (context, detail) => _body(context, detail),
            ),
          ),
          _StageChangeBar(
            applicant: widget.applicant,
            repository: _repo,
            // 성공하면 상세를 다시 받는다 — 단계 칩·레일·이력이 함께 맞춰진다
            onChanged: _reload,
          ),
        ],
      ),
    );
  }

  Widget _body(BuildContext context, ApplicantDetail detail) {
    final applicant = detail.applicant;

    return SingleChildScrollView(
      // 시안: 화면 여백 16dp
      padding: const EdgeInsets.all(AppSpace.s4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // 앱 UI 초안(2026-09-01): 지원 정보보다 먼저 "지금 어디까지
          // 왔는지". 불합격이면 레일이 나오지 않는다 — stage_rail.dart 참고
          if (StageRail.showsFor(applicant.currentStage)) ...[
            StageRail(current: applicant.currentStage),
            const SizedBox(height: AppSpace.s5),
          ],

          // 05-design §0.5: "요약문은 **상세 패널 상단**". 아래 지원 정보보다
          // 먼저 온다. NULL 이면(미생성) 자리를 만들지 않는다
          if (applicant.aiSummary != null) ...[
            ArSummaryBlock(applicant: applicant),
            const SizedBox(height: AppSpace.s3),
          ],

          DetailFieldList(
            fields: {
              if (applicant.phone != null) '연락처': applicant.phone!,
              '이메일': applicant.email,
              '학력': applicant.education ?? '—',
              '경력': applicant.careerLabel,
              if (applicant.skills.isNotEmpty)
                '기술': applicant.skills.join(' · '),
              '지원일': formatDate(applicant.createdAt),
              // 초안: 평점은 지원 정보 안의 한 줄이다. 개별 평가는
              // 아래 [평가] 화면에 있다 (시안 3번)
              '평점': ?_ratingLabel(detail),
            },
          ),

          // 웹 C7(2026-09-02)과 같은 자리 — 지원 정보 바로 다음
          const SizedBox(height: AppSpace.s3),
          FilesBlock(files: detail.files),

          const SizedBox(height: AppSpace.s3),
          MailBlock(applicantName: applicant.name),

          const SizedBox(height: AppSpace.s3),
          EmailLogBlock(applicationId: applicant.id),

          const SizedBox(height: AppSpace.s3),
          NotesBlock(
            notes: detail.notes,
            onSubmit: (body) async {
              await _repo.addNote(applicant.id, body);
              // 목록을 다시 받는다 — 내 것만 끼워 넣으면 그 사이 남이 쓴 메모가
              // 안 보인다
              _reload();
            },
          ),

          // 초안(2026-09-01): 최근 두 건은 여기서 바로 보이고,
          // 전체는 시안 2번의 별도 화면 그대로다
          const SizedBox(height: AppSpace.s3),
          StageHistoryPreview(
            history: detail.stageHistory,
            onSeeAll: () => Navigator.pushNamed(
              context,
              Routes.stageHistory,
              arguments: (applicant, widget.postingTitle),
            ),
          ),

          // 시안 3번: 개별 평가는 별도 화면이다. 초안에는 평점 한 줄만
          // 있지만 그 화면으로 들어갈 문이 여기밖에 없어 남긴다
          const SizedBox(height: AppSpace.s3),
          _LinkRow(
            icon: Icons.star_outline,
            label: '평가',
            onTap: () => Navigator.pushNamed(
              context,
              Routes.evaluations,
              arguments: applicant,
            ),
          ),
        ],
      ),
    );
  }
}

/// 상세 헤더 — 시안(2026-08-28): 왼쪽 뒤로가기 · 이름 · 오른쪽 단계 칩.
///
/// 목업(.dhead)은 오른쪽 위 X 로 닫는 오버레이였지만, 시안은 전 화면이
/// 왼쪽 뒤로가기(←)를 쓴다. 공고 → 지원자 → 상세로 파고드는 계층이라
/// 안드로이드의 뒤로가기와 방향이 같다.
class _Header extends StatelessWidget {
  const _Header({required this.applicant});

  final Applicant applicant;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: AppColors.bgElev,
        border: Border(
          bottom: BorderSide(color: AppColors.border, width: AppShape.borderW),
        ),
      ),
      child: SafeArea(
        bottom: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpace.s2,
            AppSpace.s2,
            AppSpace.s4,
            AppSpace.s2,
          ),
          child: Row(
            children: [
              _BackButton(onPressed: () => Navigator.pop(context)),
              const SizedBox(width: AppSpace.s2),
              // 05-design §7: 긴 이름은 한 줄 ellipsis
              Expanded(
                child: Text(
                  applicant.name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  softWrap: false,
                  style: const TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.h1,
                    fontWeight: FontWeight.w700,
                    letterSpacing: -0.22,
                    color: AppColors.text,
                    shadows: AppTextShadow.heading,
                  ),
                ),
              ),
              const SizedBox(width: AppSpace.s3),
              StageLabel(stage: applicant.currentStage),

              // 05-design §0.5 아르는 전 화면 공통 진입점이다. 이 화면은 하단이
              // [단계 변경] 자리라 FAB 를 놓을 곳이 없어 상단 바가 그 자리를 받는다
              const SizedBox(width: AppSpace.s2),
              Semantics(
                button: true,
                label: '아르에게 물어보기',
                child: Material(
                  color: Colors.transparent,
                  shape: const CircleBorder(),
                  clipBehavior: Clip.antiAlias,
                  child: InkWell(
                    onTap: () => showArSheet(context),
                    highlightColor: AppColors.bgSunken,
                    splashColor: AppColors.bgSunken,
                    child: const SizedBox(
                      // §9 터치 타깃 44 — 아바타는 그 안에 32 로 앉힌다
                      width: AppLayout.minTouchTarget,
                      height: AppLayout.minTouchTarget,
                      child: Center(child: ArAvatar(size: 32)),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// 뒤로가기 — 시안은 테두리 없는 맨 화살표다. 44×44 터치 타깃은 유지한다 (§9).
class _BackButton extends StatelessWidget {
  const _BackButton({required this.onPressed});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: '뒤로',
      child: Material(
        color: Colors.transparent,
        shape: const CircleBorder(),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onPressed,
          // §5: 모바일은 hover 없음 전제 — press 만 정의한다
          highlightColor: AppColors.bgSunken,
          splashColor: AppColors.bgSunken,
          child: const SizedBox(
            width: AppLayout.minTouchTarget,
            height: AppLayout.minTouchTarget,
            child: Icon(Icons.arrow_back, size: 24, color: AppColors.text),
          ),
        ),
      ),
    );
  }
}

/// 목업 `.dfoot` — 화면 아래에 붙는 단계 변경 줄.
///
/// 05-design §10: 드래그가 없는 환경의 **유일한 단계 이동 수단**이다.
/// 모바일은 칸반을 쓰지 않으므로(§9) 이 버튼이 그 자리를 대신한다.
///
/// 누르면 확인 시트가 열린다(시안 1번). **시트에서 확정해도 아직 서버에 보내지
/// 않는다** — 실제 호출은 큐 8번(API 연동)이다. 지금은 고른 값을 토스트로 되비춘다.
class _StageChangeBar extends StatefulWidget {
  const _StageChangeBar({
    required this.applicant,
    required this.repository,
    required this.onChanged,
  });

  final Applicant applicant;
  final ApplicantRepository repository;

  /// 성공하면 상세를 다시 받는다 — 단계 칩·레일·이력이 한꺼번에 맞춰진다
  final VoidCallback onChanged;

  @override
  State<_StageChangeBar> createState() => _StageChangeBarState();
}

class _StageChangeBarState extends State<_StageChangeBar> {
  /// 보내는 중 — 버튼을 잠근다. 두 번 눌러 두 번 보내면 이력이 두 줄 남는다
  bool _sending = false;

  /// 시안 1번: 고르는 순간 실행되지 않는다. 시트에서 확정해야 넘어간다.
  ///
  /// 웹은 버튼을 바로 누르면 실행되지만 앱은 시트를 한 번 더 거친다 — 폰은
  /// 스크롤하다 손가락이 스치기 쉽고, **불합격은 메일이 나가 되돌릴 수 없다**.
  Future<void> _openSheet(BuildContext context) async {
    // 시트가 닫히면 그 context 는 못 쓴다. 열기 전에 잡아 둔다
    final messenger = ScaffoldMessenger.of(context);

    final picked = await showStageChangeSheet(
      context,
      applicant: widget.applicant,
    );
    if (picked == null || !mounted) return;

    setState(() => _sending = true);

    try {
      await widget.repository.changeStage(
        widget.applicant.id,
        picked.stage,
        reason: picked.reason,
      );
      if (!mounted) return;

      // 05-design §6: 단계 이동 성공·실패는 토스트로 — 조용히 지나가면 안 된다
      messenger.showSnackBar(
        SnackBar(
          content: Text(
            '${widget.applicant.name} — ${picked.stage.label}으로 옮겼습니다',
          ),
        ),
      );
      widget.onChanged();
    } on ApiError catch (e) {
      if (!mounted) return;
      // 서버가 거절한 이유를 그대로 보여 준다 — 갈 수 없는 단계(409)나
      // 사유 누락(422)은 사용자가 할 일이 서로 다르다
      messenger.showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: AppColors.bgElev,
        border: Border(
          top: BorderSide(color: AppColors.border, width: AppShape.borderW),
        ),
      ),
      // SafeArea 를 높이 제약 **바깥**에 둔다. 안쪽에 두면 내비게이션 바가
      // 차지하는 만큼 72px 안에서 깎여 버튼 위아래 여백이 사라진다
      child: SafeArea(
        top: false,
        child: Container(
          constraints: const BoxConstraints(minHeight: 72),
          padding: const EdgeInsets.symmetric(horizontal: AppSpace.s5),
          alignment: Alignment.center,
          child: SizedBox(
            width: double.infinity,
            height: AppLayout.minTouchTarget,
            child: FilledButton(
              onPressed: _sending ? null : () => _openSheet(context),
              child: _sending
                  // 글자를 지우지 않고 그 자리에 스피너를 둔다 —
                  // 버튼 크기가 변하면 눌린 자리가 흔들린다(로그인과 같은 방식)
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: AppColors.bgElev,
                      ),
                    )
                  : const Text('단계 변경'),
            ),
          ),
        ),
      ),
    );
  }
}

/// 다른 화면으로 가는 줄 — 단계 이력·평가.
///
/// 시안 2·3번이 둘을 별도 화면으로 뺐다. 상세에 그대로 끼우면
/// 코멘트가 길어 지원 정보가 아래로 밀린다.
class _LinkRow extends StatelessWidget {
  const _LinkRow({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.bgElev,
      shape: const RoundedRectangleBorder(
        borderRadius: AppShape.card,
        side: BorderSide(color: AppColors.border, width: AppShape.borderW),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        // §5: 모바일은 hover 없음 전제 — press 만 정의한다
        highlightColor: AppColors.bgSunken,
        splashColor: AppColors.bgSunken,
        child: Container(
          // §9 터치 타깃
          constraints: const BoxConstraints(
            minHeight: AppLayout.minTouchTarget,
          ),
          padding: const EdgeInsets.all(AppSpace.s4),
          child: Row(
            children: [
              Icon(icon, size: 20, color: AppColors.textSub),
              const SizedBox(width: AppSpace.s3),
              Expanded(
                child: Text(
                  label,
                  style: const TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.body,
                    fontWeight: AppType.wSemiBold,
                    color: AppColors.text,
                  ),
                ),
              ),
              const Icon(
                Icons.chevron_right,
                size: 20,
                color: AppColors.textSub,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
