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

import '../data/mock_data.dart';
import '../models/applicant.dart';
import '../models/stage.dart';
import '../theme/tokens.dart';
import '../utils/format.dart';
import '../widgets/applicant_card.dart';

class ApplicantsSearchScreen extends StatefulWidget {
  const ApplicantsSearchScreen({super.key, this.onOpenApplicant});

  final void Function(Applicant applicant, String postingTitle)? onOpenApplicant;

  @override
  State<ApplicantsSearchScreen> createState() => _ApplicantsSearchScreenState();
}

class _ApplicantsSearchScreenState extends State<ApplicantsSearchScreen> {
  final _controller = TextEditingController();

  /// null = 전체. 05-design 은 지원자 화면에 칸반을 두지 않으므로 필터는 칩뿐이다
  Stage? _stage;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  String _postingTitleOf(Applicant a) =>
      mockPostings.firstWhere((p) => p.id == a.jobPostingId).title;

  List<Applicant> get _results {
    final term = _controller.text.trim().toLowerCase();
    return mockApplicants.where((a) {
      if (_stage != null && a.currentStage != _stage) return false;
      if (term.isEmpty) return true;
      // 웹 placeholder 가 "이름 또는 공고 검색" 이라 두 곳만 본다
      return a.name.toLowerCase().contains(term) ||
          _postingTitleOf(a).toLowerCase().contains(term);
    }).toList();
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
                onChanged: (_) => setState(() {}),
                onClear: () => setState(_controller.clear),
              ),
              _StageChips(
                selected: _stage,
                onSelected: (s) => setState(() => _stage = s),
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
            formatItemCount(results.length),
            style: const TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.caption,
              fontFeatures: AppType.tabularNums,
              color: AppColors.textSub,
            ),
          ),
        ),

        Expanded(
          child: results.isEmpty
              ? _Empty(searching: searching)
              : ListView.separated(
                  padding: const EdgeInsets.fromLTRB(
                    AppSpace.s4,
                    AppSpace.s2,
                    AppSpace.s4,
                    AppSpace.s4,
                  ),
                  itemCount: results.length,
                  separatorBuilder: (_, _) => const SizedBox(height: AppSpace.s3),
                  itemBuilder: (_, i) {
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
                ),
        ),
      ],
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
        prefixIcon: const Icon(Icons.search, size: 20, color: AppColors.textSub),
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
          borderSide: BorderSide(color: AppColors.border, width: AppShape.borderW),
        ),
        enabledBorder: const OutlineInputBorder(
          borderRadius: AppShape.ctl,
          borderSide: BorderSide(color: AppColors.border, width: AppShape.borderW),
        ),
        focusedBorder: const OutlineInputBorder(
          borderRadius: AppShape.ctl,
          borderSide: BorderSide(color: AppColors.leaf, width: AppShape.borderW),
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
  const _Chip({required this.label, required this.selected, required this.onTap});

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
