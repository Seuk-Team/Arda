/// 검색 입력칸 — **공고별 지원자**가 쓴다.
///
/// 웹 `PostingApplicants.tsx` 의 "검색어 입력" 을 옮긴 것이다. 한 공고에 22명이
/// 쌓이면 단계 탭만으로는 못 찾는다.
///
/// 지원자 탭(`applicants_search_screen.dart`)에도 같은 모양의 검색칸이 있지만
/// 그 화면 안의 `_SearchField` 로 따로 있다. **합치지 않았다** — 도는 코드를
/// 건드리지 않기로 했고(CLAUDE.md 리팩터링 금지), 지금 필요한 건 없던 자리에
/// 검색을 더하는 것뿐이다. 둘을 합치는 것은 별도 작업이다.
///
/// [hintText] 는 자리마다 다르다 — 전 공고는 "이름 또는 공고", 여기는 이름뿐이다.
library;

import 'package:flutter/material.dart';

import '../theme/tokens.dart';

/// 어디를 뒤질지 — 웹 `PostingApplicants.tsx` 의 `전체 / 이름 / 이메일` 선택.
///
/// 이메일로 찾는 일이 실제로 있다. 같은 이름이 둘일 때, 메일함에서 주소만 알 때.
enum SearchScope {
  all('전체'),
  name('이름'),
  email('이메일');

  const SearchScope(this.label);

  final String label;
}

class SearchField extends StatelessWidget {
  const SearchField({
    super.key,
    required this.controller,
    required this.hintText,
    required this.onChanged,
    required this.onClear,
    this.scope,
    this.onScopeChanged,
  });

  /// 주면 왼쪽에 범위 선택이 붙는다. 안 주면 예전처럼 검색칸만
  final SearchScope? scope;
  final ValueChanged<SearchScope>? onScopeChanged;

  final TextEditingController controller;

  /// 웹 문구를 그대로 쓴다
  final String hintText;

  final ValueChanged<String> onChanged;
  final VoidCallback onClear;

  static const _outline = OutlineInputBorder(
    borderRadius: AppShape.ctl,
    borderSide: BorderSide(color: AppColors.border, width: AppShape.borderW),
  );

  @override
  Widget build(BuildContext context) {
    final field = _field();
    if (scope == null || onScopeChanged == null) return field;

    // 웹은 선택과 입력칸이 한 상자 안에 나란히 있다. 375px 에서도 같은 줄에
    // 두되 선택 쪽을 최소 폭으로 눌러 입력칸을 넓게 남긴다
    return Row(
      children: [
        _ScopePicker(value: scope!, onChanged: onScopeChanged!),
        const SizedBox(width: AppSpace.s2),
        Expanded(child: field),
      ],
    );
  }

  Widget _field() {
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
        hintText: hintText,
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
        // 지울 것이 있을 때만 X 를 낸다 — 빈 칸에 X 가 있으면 뭘 지우는지 모른다
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
        border: _outline,
        enabledBorder: _outline,
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

/// 검색 범위 선택 — 웹의 `<select>` 자리.
///
/// 값이 셋뿐이라 드롭다운 대신 눌러서 고르는 메뉴로 둔다. 셋을 칩으로 펴면
/// 검색칸이 좁아지고, 폰에서 검색칸이 좁은 쪽이 더 불편하다.
class _ScopePicker extends StatelessWidget {
  const _ScopePicker({required this.value, required this.onChanged});

  final SearchScope value;
  final ValueChanged<SearchScope> onChanged;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.bgSunken,
      shape: const RoundedRectangleBorder(
        borderRadius: AppShape.ctl,
        side: BorderSide(color: AppColors.border, width: AppShape.borderW),
      ),
      clipBehavior: Clip.antiAlias,
      child: PopupMenuButton<SearchScope>(
        initialValue: value,
        onSelected: onChanged,
        tooltip: '검색 범위',
        position: PopupMenuPosition.under,
        color: AppColors.bgElev,
        itemBuilder: (_) => [
          for (final s in SearchScope.values)
            PopupMenuItem(
              value: s,
              child: Text(
                s.label,
                style: TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.sm,
                  // 고른 것만 잎초록 (§1 색은 판단에만 — 여기선 현재 선택 표시)
                  fontWeight: s == value ? AppType.wSemiBold : AppType.wRegular,
                  color: s == value ? AppColors.leaf : AppColors.text,
                ),
              ),
            ),
        ],
        child: Container(
          // §9 터치 타깃 44. 검색칸(46)과 높이를 맞춘다
          height: 46,
          padding: const EdgeInsets.only(left: AppSpace.s3, right: AppSpace.s1),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                value.label,
                softWrap: false,
                style: const TextStyle(
                  fontFamily: AppType.fontFamily,
                  fontSize: AppType.sm,
                  color: AppColors.text,
                ),
              ),
              const Icon(
                Icons.arrow_drop_down,
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
