/// 지원자 상세의 블록들 — 아르의 요약 · 시스템(메일 이력) · 메모.
///
/// 배포판 웹 상세 패널(2026-09-01)을 375px 로 옮긴 것이고, 값과 배치는
/// 05-design·01-erd 를 따른다.
library;

import 'package:flutter/material.dart';

import '../api/api_error.dart';
import '../data/mock_data.dart';
import '../models/ai_summary.dart';
import '../models/applicant.dart';
import '../models/applicant_file.dart';
import '../models/application_note.dart';
import '../models/email_log.dart';
import '../models/stage_history.dart';
import '../screens/mail_compose_screen.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';

/// 아르의 요약 — 05-design §1 (2026-09-01 팀장 확정).
///
/// > 앰버는 **사람의 확정을 기다리는 것**에만 쓴다. 읽기만 하는 AI 산출물에는
/// > 쓰지 않는다 — 다른 섹션과 같은 정보 블록(`--bg-sunken` + `--border-soft`)으로
/// > 두고 출처는 제목("아르의 요약")이 말한다.
///
/// 액션을 요구하지 않는 것에 앰버를 쓰면 "뭘 눌러야 하나"로 읽힌다.
/// 아르 화면의 명단 카드도 같은 이유로 정보 블록이다 — 확정 버튼이 없다.
class ArSummaryBlock extends StatelessWidget {
  const ArSummaryBlock({super.key, required this.applicant});

  final Applicant applicant;

  @override
  Widget build(BuildContext context) {
    final summary = applicant.aiSummary;
    if (summary == null) return const SizedBox.shrink();

    final at = applicant.aiSummaryAt;
    final model = applicant.aiSummaryModel;

    return Container(
      padding: const EdgeInsets.all(AppSpace.s4),
      decoration: BoxDecoration(
        color: AppColors.bgSunken,
        borderRadius: AppShape.card,
        border: Border.all(
          color: AppColors.borderSoft,
          width: AppShape.borderW,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: [
              const Expanded(
                child: Text(
                  '아르의 요약',
                  style: TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.h2,
                    fontWeight: FontWeight.w700,
                    color: AppColors.text,
                    shadows: AppTextShadow.heading,
                  ),
                ),
              ),
              // 접수 시 1회 생성·저장, 재생성은 명시적 버튼으로만(§0.5).
              // 큐 8 에서 POST /agent/applications/{id}/summarize 가 붙는다
              const Text(
                '다시 생성',
                style: TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.sm,
                  fontWeight: AppType.wSemiBold,
                  color: AppColors.textSub,
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpace.s3),
          _SummaryBody(summary: AiSummary.parse(summary)),
          if (at != null) ...[
            const SizedBox(height: AppSpace.s3),
            Text(
              // 모델명은 발표 때 근거로 쓰는 값이다(ERD ai_summary_model).
              // 프롬프트 태그까지는 화면에 길어 모델까지만 자른다
              model == null
                  ? '${formatDate(at)} 생성'
                  : '${formatDate(at)} 생성 · ${model.split('/').first}',
              style: const TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.caption,
                fontFeatures: AppType.tabularNums,
                color: AppColors.textSub,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// 요약 본문 — 웹 `ApplicantPanel.tsx` 의 `AiSummaryBody` 와 같은 순서·같은 라벨.
///
/// 요지는 문단, 강점·확인 필요는 목록이다. **면접 확인 포인트는 그리지 않는다**
/// (05-design §0.5, 6905c37).
class _SummaryBody extends StatelessWidget {
  const _SummaryBody({required this.summary});

  final AiSummary summary;

  static const _bodyStyle = TextStyle(
    fontFamily: AppType.fontFamily,
    fontSize: AppType.sm,
    height: 1.6,
    color: AppColors.text,
  );

  @override
  Widget build(BuildContext context) {
    if (summary.insufficient) {
      // 웹과 같은 문구 — 요약이 없는 것과 못 만든 것은 다르다
      return const Text('자기소개 등 자료가 부족해 요약을 만들지 못했습니다.', style: _bodyStyle);
    }

    // 모델이 규격을 벗어난 경우. 담당자가 내용은 읽을 수 있어야 한다
    if (summary.isRawText) return Text(summary.raw!, style: _bodyStyle);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (summary.gist != null) Text(summary.gist!, style: _bodyStyle),
        if (summary.fit.isNotEmpty)
          _SummaryList(label: '강점', items: summary.fit),
        if (summary.concerns.isNotEmpty)
          _SummaryList(label: '확인 필요', items: summary.concerns),
      ],
    );
  }
}

class _SummaryList extends StatelessWidget {
  const _SummaryList({required this.label, required this.items});

  final String label;
  final List<String> items;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: AppSpace.s3),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.caption,
              fontWeight: FontWeight.w700,
              color: AppColors.textSub,
            ),
          ),
          const SizedBox(height: AppSpace.s1),
          for (final item in items)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpace.s1),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // 웹은 <ul> 이다. 앱에는 목록 마커가 없어 가운뎃점으로 대신한다
                  const Text('·', style: _SummaryBody._bodyStyle),
                  const SizedBox(width: AppSpace.s2),
                  Expanded(child: Text(item, style: _SummaryBody._bodyStyle)),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

/// 첨부 파일 — 웹 `ApplicantPanel.tsx`(C7, 2026-09-02)를 옮긴 것.
/// 웹과 같이 **지원 정보 바로 다음**이다.
///
/// 웹은 한 줄에 이름·종류·크기를 다 넣지만 375px 엔 안 들어간다 —
/// 이름 위, 종류·크기 아래 두 줄로 나눈다.
///
/// **비어 있어도 블록을 그린다.** 담당자가 직접 등록한 사람(D6)은 파일이 없는데,
/// 블록째 사라지면 "아직 안 붙었나" 와 "원래 없다" 가 구별되지 않는다.
class FilesBlock extends StatelessWidget {
  const FilesBlock({super.key, required this.files});

  /// 상세 응답이 함께 준다 — 화면이 목데이터를 뒤지지 않는다 (큐 8, 2026-09-02)
  final List<ApplicantFile> files;

  @override
  Widget build(BuildContext context) {
    return DetailPanel(
      title: '첨부 파일',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (files.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: AppSpace.s2),
              child: Text(
                // 웹과 같은 문구
                '첨부된 파일이 없습니다.',
                style: TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.sm,
                  color: AppColors.textSub,
                ),
              ),
            )
          else
            for (var i = 0; i < files.length; i++) ...[
              if (i > 0) const SizedBox(height: AppSpace.s2),
              _FileRow(file: files[i]),
            ],
        ],
      ),
    );
  }
}

class _FileRow extends StatelessWidget {
  const _FileRow({required this.file});

  final ApplicantFile file;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.bgElev,
      shape: const RoundedRectangleBorder(
        borderRadius: AppShape.ctl,
        side: BorderSide(color: AppColors.border, width: AppShape.borderW),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        // 큐 8: POST /files/{id}/presign-download → 받은 URL 을 브라우저로 넘긴다
        onTap: () => ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('${file.filename} (아직 열 수 없음)'))),
        // §5: 모바일은 hover 없음 전제 — press 만 정의한다
        highlightColor: AppColors.bgSunken,
        splashColor: AppColors.bgSunken,
        child: Container(
          constraints: const BoxConstraints(minHeight: 56),
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpace.s3,
            vertical: AppSpace.s2,
          ),
          child: Row(
            children: [
              const Icon(
                Icons.description_outlined,
                size: 20,
                color: AppColors.textSub,
              ),
              const SizedBox(width: AppSpace.s3),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      // 긴 파일명은 두 줄까지 — 확장자가 잘리면 무슨 파일인지 모른다
                      file.filename,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontFamily: AppType.fontFamily,
                        fontSize: AppType.sm,
                        fontWeight: AppType.wSemiBold,
                        height: 1.4,
                        color: AppColors.text,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${file.kind.label} · ${file.sizeLabel}',
                      style: const TextStyle(
                        fontFamily: AppType.fontFamily,
                        fontSize: AppType.caption,
                        fontFeatures: AppType.tabularNums,
                        color: AppColors.textSub,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// 메일 — 단계별 안내를 손으로 보낸다(G4).
///
/// 앱 UI 초안(2026-09-01)이 지원 정보와 시스템 사이에 넣었다. 자동 발송은
/// 단계 변경에 붙어 있고(`stage_history.mail_queued`), 이 줄은 그 밖에서
/// 다시 보내야 할 때 쓴다 — 접수 확인이 실패했거나 안내를 다시 보낼 때.
///
/// **불합격만 적갈**이다 (§1 색은 판단에만). 되돌릴 수 없는 메일이라
/// 나머지와 같은 무채로 두면 잘못 누른다.
class MailBlock extends StatelessWidget {
  const MailBlock({
    super.key,
    required this.applicantName,
    required this.onPick,
  });

  final String applicantName;

  /// 프리셋을 고르면 부르는 쪽이 메일 쓰기 화면을 연다.
  /// **여기서 바로 보내지 않는다** — 프리필 → 편집 → 확인을 거친다(웹과 같다)
  final ValueChanged<MailPreset> onPick;

  @override
  Widget build(BuildContext context) {
    return DetailPanel(
      title: '메일',
      child: Wrap(
        spacing: AppSpace.s2,
        runSpacing: AppSpace.s2,
        children: [
          for (final preset in MailPreset.values)
            _MailButton(
              label: preset.label,
              danger: preset.danger,
              onTap: () => onPick(preset),
            ),
        ],
      ),
    );
  }
}

class _MailButton extends StatelessWidget {
  const _MailButton({
    required this.label,
    required this.danger,
    required this.onTap,
  });

  final String label;
  final bool danger;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final tone = danger ? AppColors.danger : AppColors.text;

    return Material(
      color: AppColors.bgElev,
      shape: RoundedRectangleBorder(
        borderRadius: AppShape.ctl,
        side: BorderSide(
          color: danger ? AppColors.danger : AppColors.border,
          width: AppShape.borderW,
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        // §5: 모바일은 hover 없음 전제 — press 만 정의한다
        highlightColor: AppColors.bgSunken,
        splashColor: AppColors.bgSunken,
        child: SizedBox(
          // §9 터치 타깃 — 초안의 36 은 웹 값이라 44 로 올린다
          height: AppLayout.minTouchTarget,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: AppSpace.s4),
            // Container 에 alignment 를 주면 Wrap 안에서 허용 폭 끝까지 늘어나
            // 버튼이 한 줄에 하나씩 깔린다. widthFactor 1 로 글자 폭에 맞춘다
            child: Center(
              widthFactor: 1,
              child: Text(
                label,
                style: TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.sm,
                  fontWeight: AppType.wSemiBold,
                  color: tone,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// 시스템 — 메일 발송 이력. **실패만 적갈**이다.
/// 메일이 안 나간 것을 놓치면 지원자가 연락을 받지 못한다.
class EmailLogBlock extends StatelessWidget {
  const EmailLogBlock({super.key, required this.applicationId});

  final int applicationId;

  @override
  Widget build(BuildContext context) {
    final logs = mockEmailLogs[applicationId] ?? const <EmailLog>[];
    if (logs.isEmpty) return const SizedBox.shrink();

    return DetailPanel(
      title: '시스템',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (var i = 0; i < logs.length; i++)
            Container(
              decoration: BoxDecoration(
                border: i == 0 ? null : const Border(top: _softLine),
              ),
              padding: const EdgeInsets.symmetric(vertical: AppSpace.s2),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.baseline,
                textBaseline: TextBaseline.alphabetic,
                children: [
                  Text(
                    logs[i].status.label,
                    style: TextStyle(
                      fontFamily: AppType.fontFamily,
                      fontSize: AppType.caption,
                      fontWeight: FontWeight.w700,
                      // §1: 색은 판단에만. 실패만 적갈, 발송은 잎초록
                      color: switch (logs[i].status) {
                        EmailStatus.failed => AppColors.danger,
                        EmailStatus.sent => AppColors.leaf,
                        EmailStatus.queued => AppColors.textSub,
                      },
                    ),
                  ),
                  const SizedBox(width: AppSpace.s2),
                  Text(
                    formatDate(logs[i].createdAt),
                    style: const TextStyle(
                      fontFamily: AppType.fontFamily,
                      fontSize: AppType.caption,
                      fontFeatures: AppType.tabularNums,
                      color: AppColors.textSub,
                    ),
                  ),
                  const SizedBox(width: AppSpace.s2),
                  Expanded(
                    child: Text(
                      logs[i].subject,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      softWrap: false,
                      style: const TextStyle(
                        fontFamily: AppType.fontFamily,
                        fontSize: AppType.caption,
                        color: AppColors.text,
                      ),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

/// 메모 — 05-design: "작성자 · 날짜 + 본문" **시간순 목록**.
///
/// 웹은 입력칸 하나지만 ERD 는 행을 쌓는 구조다(`application_notes`).
/// 한 문서를 공동 편집하지 않고 각자 행을 추가한다(ADR-0005)므로 목록이 맞다.
class NotesBlock extends StatefulWidget {
  const NotesBlock({super.key, required this.notes, required this.onSubmit});

  /// **전용 엔드포인트**에서 받은 것 — 상세에 박혀 오는 메모와 달리
  /// 작성자 이름이 들어 있다 (큐 8, 2026-09-02)
  final List<ApplicationNote> notes;

  /// 본문을 서버로 보낸다. 성공하면 상세를 다시 받아 목록이 갱신된다
  final Future<void> Function(String body) onSubmit;

  @override
  State<NotesBlock> createState() => _NotesBlockState();
}

class _NotesBlockState extends State<NotesBlock> {
  final _draft = TextEditingController();
  bool _sending = false;

  @override
  void initState() {
    super.initState();
    // 빈 칸이면 보내기가 잠긴다 — 글자마다 다시 그려야 그게 보인다
    _draft.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _draft.dispose();
    super.dispose();
  }

  bool get _canSubmit => !_sending && _draft.text.trim().isNotEmpty;

  Future<void> _submit() async {
    if (!_canSubmit) return;
    setState(() => _sending = true);
    final messenger = ScaffoldMessenger.of(context);

    try {
      await widget.onSubmit(_draft.text.trim());
      if (!mounted) return;
      // 보낸 것을 지운다 — 남아 있으면 두 번 보내기 쉽다
      _draft.clear();
    } on ApiError catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  List<ApplicationNote> get notes => widget.notes;

  @override
  Widget build(BuildContext context) {
    return DetailPanel(
      title: '메모',
      trailing: notes.isEmpty ? null : formatItemCount(notes.length),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (notes.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: AppSpace.s2),
              child: Text(
                '아직 메모가 없습니다.',
                style: TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.sm,
                  color: AppColors.textSub,
                ),
              ),
            )
          else
            for (var i = 0; i < notes.length; i++)
              Container(
                decoration: BoxDecoration(
                  border: i == 0 ? null : const Border(top: _softLine),
                ),
                padding: const EdgeInsets.symmetric(vertical: AppSpace.s3),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${notes[i].authorName} · ${formatDate(notes[i].createdAt)}',
                      style: const TextStyle(
                        fontFamily: AppType.fontFamily,
                        fontSize: AppType.caption,
                        fontFeatures: AppType.tabularNums,
                        color: AppColors.textSub,
                      ),
                    ),
                    const SizedBox(height: AppSpace.s1),
                    Text(
                      notes[i].body,
                      style: const TextStyle(
                        fontFamily: AppType.fontFamily,
                        fontSize: AppType.sm,
                        height: 1.55,
                        color: AppColors.text,
                      ),
                    ),
                  ],
                ),
              ),

          const SizedBox(height: AppSpace.s3),
          // 큐 8(2026-09-02): 살아 있는 입력칸이 됐다
          TextField(
            controller: _draft,
            enabled: !_sending,
            // 메모는 여러 줄이 흔하다 — 한 줄로 두면 긴 메모를 못 읽으며 쓴다
            minLines: 2,
            maxLines: 5,
            textInputAction: TextInputAction.newline,
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.sm,
              height: 1.55,
              color: AppColors.text,
            ),
            decoration: const InputDecoration(
              isDense: true,
              filled: true,
              fillColor: AppColors.bgSunken,
              hintText: '메모 남기기',
              hintStyle: TextStyle(
                fontFamily: AppType.fontFamily,
                fontSize: AppType.sm,
                color: AppColors.textSub,
              ),
              contentPadding: EdgeInsets.symmetric(
                horizontal: AppSpace.s3,
                vertical: AppSpace.s3,
              ),
              border: OutlineInputBorder(
                borderRadius: AppShape.ctl,
                borderSide: BorderSide(
                  color: AppColors.border,
                  width: AppShape.borderW,
                ),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: AppShape.ctl,
                borderSide: BorderSide(
                  color: AppColors.border,
                  width: AppShape.borderW,
                ),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: AppShape.ctl,
                borderSide: BorderSide(
                  color: AppColors.leaf,
                  width: AppShape.borderW,
                ),
              ),
            ),
          ),
          const SizedBox(height: AppSpace.s2),
          Align(
            alignment: Alignment.centerRight,
            child: SizedBox(
              height: AppLayout.minTouchTarget,
              child: FilledButton(
                onPressed: _canSubmit ? _submit : null,
                child: _sending
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: AppColors.bgElev,
                        ),
                      )
                    : const Text('남기기'),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// 단계 이력 — **최근 두 건만** 보여 주고 나머지는 별도 화면으로 넘긴다.
///
/// 시안 2번이 이력을 통째로 별도 화면으로 뺐고, 앱 UI 초안(2026-09-01)이
/// 상세에 최근 몇 줄을 되살렸다. 상세를 여는 가장 흔한 이유가 "언제 넘어왔지"
/// 인데, 그 답을 보려고 화면을 하나 더 열게 하지 않으려는 것이다.
/// 전체 목록은 그대로 [onSeeAll] 뒤에 있다.
class StageHistoryPreview extends StatelessWidget {
  const StageHistoryPreview({
    super.key,
    required this.history,
    required this.onSeeAll,
  });

  /// **최신이 위**로 정렬된 것 — 저장소가 뒤집어 준다 (서버는 오래된 순)
  final List<StageHistory> history;

  final VoidCallback onSeeAll;

  /// 초안이 두 줄이다. 더 늘리면 아래 [단계 변경] 이 멀어진다
  static const _previewCount = 2;

  @override
  Widget build(BuildContext context) {
    final all = history;
    if (all.isEmpty) return const SizedBox.shrink();

    // 최신이 위 — 앞에서 자르면 최근 두 건이다
    final shown = all.take(_previewCount).toList();

    return DetailPanel(
      title: '단계 이력',
      trailing: '전체 →',
      onTrailingTap: onSeeAll,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final h in shown)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: AppSpace.s1),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: 60,
                    child: Text(
                      formatMonthDay(h.createdAt),
                      style: const TextStyle(
                        fontFamily: AppType.fontFamily,
                        fontSize: AppType.sm,
                        fontFeatures: AppType.tabularNums,
                        color: AppColors.textSub,
                      ),
                    ),
                  ),
                  const SizedBox(width: AppSpace.s3),
                  Expanded(
                    child: Text(
                      // from_stage 가 NULL 이면 최초 접수다 (ERD)
                      h.fromStage == null
                          ? '${h.toStage.label} · 지원자 제출'
                          : '${h.fromStage!.label} → ${h.toStage.label}',
                      style: const TextStyle(
                        fontFamily: AppType.fontFamily,
                        fontSize: AppType.sm,
                        height: 1.5,
                        color: AppColors.text,
                      ),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

/// 상세의 흰 카드 껍데기 — 05-design §4.
class DetailPanel extends StatelessWidget {
  const DetailPanel({
    super.key,
    required this.title,
    required this.child,
    this.trailing,
    this.onTrailingTap,
  });

  final String title;
  final Widget child;

  /// 제목 오른쪽 — 건수("2건") 또는 다른 화면으로 가는 링크("전체 →")
  final String? trailing;

  /// 주면 [trailing] 이 링크가 된다 (잎초록 + 44 터치 타깃)
  final VoidCallback? onTrailingTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpace.s4),
      decoration: BoxDecoration(
        color: AppColors.bgElev,
        borderRadius: AppShape.card,
        border: Border.all(color: AppColors.border, width: AppShape.borderW),
        boxShadow: AppShadow.card,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            // 링크가 붙으면 그쪽이 44 라 베이스라인을 맞출 수 없다 — 가운데로 건다
            crossAxisAlignment: onTrailingTap == null
                ? CrossAxisAlignment.baseline
                : CrossAxisAlignment.center,
            textBaseline: TextBaseline.alphabetic,
            children: [
              Expanded(
                child: Text(
                  title,
                  style: const TextStyle(
                    fontFamily: AppType.fontFamily,
                    fontSize: AppType.h2,
                    fontWeight: FontWeight.w700,
                    color: AppColors.text,
                    shadows: AppTextShadow.heading,
                  ),
                ),
              ),
              if (trailing != null)
                if (onTrailingTap == null)
                  Text(
                    trailing!,
                    style: const TextStyle(
                      fontFamily: AppType.fontFamily,
                      fontSize: AppType.sm,
                      fontFeatures: AppType.tabularNums,
                      color: AppColors.textSub,
                    ),
                  )
                else
                  Material(
                    color: Colors.transparent,
                    borderRadius: AppShape.ctl,
                    clipBehavior: Clip.antiAlias,
                    child: InkWell(
                      onTap: onTrailingTap,
                      // §5: 모바일은 hover 없음 전제 — press 만 정의한다
                      highlightColor: AppColors.bgSunken,
                      splashColor: AppColors.bgSunken,
                      child: Container(
                        // §9 터치 타깃 44 — 제목 줄이 그만큼 높아진다
                        constraints: const BoxConstraints(
                          minHeight: AppLayout.minTouchTarget,
                        ),
                        padding: const EdgeInsets.symmetric(
                          horizontal: AppSpace.s2,
                        ),
                        alignment: Alignment.center,
                        child: Text(
                          trailing!,
                          style: const TextStyle(
                            fontFamily: AppType.fontFamily,
                            fontSize: AppType.sm,
                            fontWeight: AppType.wSemiBold,
                            color: AppColors.leaf,
                          ),
                        ),
                      ),
                    ),
                  ),
            ],
          ),
          const SizedBox(height: AppSpace.s3),
          child,
        ],
      ),
    );
  }
}

/// 블록 안 행 사이 실선 — 카드 테두리(`--border`)보다 옅다.
const _softLine = BorderSide(
  color: AppColors.borderSoft,
  width: AppShape.borderW,
);
