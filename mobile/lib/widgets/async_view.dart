/// 05-design §6 세 상태 — 로딩 · 빈 · 오류. **화면마다 다시 만들지 않는다.**
///
/// 큐 8 에서 모든 화면이 같은 세 상태를 갖게 되는데, 화면마다 따로 그리면
/// 문구와 간격이 조금씩 달라진다. 여기 한 번만 두고 **빈 문구만** 화면이 준다.
///
/// 문구 규칙(앱 UI 초안 메모, 웹 소스에서 가져온 것):
/// - 로딩 → "불러오는 중…"
/// - 오류 → 서버가 준 문구 + **[다시 시도]**. 웹엔 없지만 앱엔 F5 가 없다
/// - 빈 → 화면마다 다르다 (공고 "등록된 공고가 없습니다." 등)
library;

import 'package:flutter/material.dart';

import '../theme/tokens.dart';

/// [future] 를 기다려 세 상태 중 하나를 그린다.
///
/// [onRetry] 는 새 Future 를 만들어야 한다 — 이미 실패한 Future 를 다시
/// 기다려 봐야 같은 실패가 나온다.
class AsyncView<T> extends StatelessWidget {
  const AsyncView({
    super.key,
    required this.future,
    required this.builder,
    required this.onRetry,
    required this.emptyMessage,
    this.isEmpty,
  });

  final Future<T> future;
  final Widget Function(BuildContext context, T data) builder;
  final VoidCallback onRetry;

  /// 이 화면의 빈 문구. 화면마다 다르다
  final String emptyMessage;

  /// 비었는지 판단하는 법. 안 주면 빈 상태를 쓰지 않는다
  final bool Function(T data)? isEmpty;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<T>(
      future: future,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const _Loading();
        }
        if (snapshot.hasError) {
          return _Error(error: snapshot.error!, onRetry: onRetry);
        }

        final data = snapshot.data as T;
        if (isEmpty?.call(data) ?? false) {
          return _Empty(message: emptyMessage);
        }
        return builder(context, data);
      },
    );
  }
}

class _Loading extends StatelessWidget {
  const _Loading();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          CircularProgressIndicator(color: AppColors.leaf),
          SizedBox(height: AppSpace.s4),
          Text(
            // 웹과 같은 문구. 말줄임표는 한 글자(…)다 — 점 셋(...)과 폭이 다르다
            '불러오는 중…',
            style: TextStyle(
              fontFamily: AppType.fontFamily,
              fontSize: AppType.sm,
              color: AppColors.textSub,
            ),
          ),
        ],
      ),
    );
  }
}

/// 오류 — 서버가 준 문구를 쓴다. 우리 백엔드는 한국어로 답한다.
class _Error extends StatelessWidget {
  const _Error({required this.error, required this.onRetry});

  final Object error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    // ApiError 는 message 를 들고 있다. 그 밖의 예외는 개발 중 실수라
    // 화면에 그대로 내보이지 않는다
    final message = switch (error) {
      final Exception e when e.toString().startsWith('ApiError:') =>
        e.toString().replaceFirst('ApiError: ', ''),
      _ => '불러오지 못했습니다.',
    };

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpace.s5),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              message,
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
              child: FilledButton(
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

class _Empty extends StatelessWidget {
  const _Empty({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
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
