import 'package:flutter/material.dart';

import '../routes.dart';

/// 공고 리스트 — 앱의 첫 화면.
///
/// **뼈대 단계다.** 목록·카드는 다음 큐(목데이터 화면)에서 만든다.
/// 지금은 화면이 존재하고 다음 화면으로 넘어간다는 것만 증명한다.
class PostingsScreen extends StatelessWidget {
  const PostingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('채용 공고')),
      body: Center(
        child: FilledButton(
          onPressed: () => Navigator.pushNamed(context, Routes.applicants),
          child: const Text('지원자 보기'),
        ),
      ),
    );
  }
}
