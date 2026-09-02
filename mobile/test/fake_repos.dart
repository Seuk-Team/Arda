// 테스트용 가짜 저장소 — 네트워크를 타지 않는다.
//
// 큐 8 로 화면이 서버에서 받아 오기 시작했다. 화면 테스트가 그대로면 매번
// 실서버에 붙으려 한다. 여기서 **기존 목데이터를 그대로 돌려주어**, 화면
// 테스트가 큐 8 전과 같은 값을 보게 한다 — 화면 규칙을 보는 테스트가
// 데이터가 바뀌었다고 깨질 이유가 없다.

import 'package:arda/data/mock_data.dart';
import 'package:arda/data/applicant_repository.dart';
import 'package:arda/data/posting_repository.dart';
import 'package:arda/models/applicant.dart';
import 'package:arda/models/job_posting.dart';

class FakePostingRepository implements PostingRepository {
  FakePostingRepository({
    this.postings,
    this.error,
    this.delay = Duration.zero,
  });

  /// 안 주면 목데이터 그대로
  final List<JobPosting>? postings;

  /// 주면 목록 요청이 이걸로 실패한다 — 오류 상태를 볼 때
  final Object? error;

  /// 로딩 상태를 볼 수 있게 늦춘다
  final Duration delay;

  @override
  Future<List<PostingWithCounts>> list() async {
    if (delay > Duration.zero) await Future<void>.delayed(delay);
    if (error != null) throw error!;

    final items = postings ?? mockPostings;
    return [
      for (final p in items)
        PostingWithCounts(posting: p, counts: postingCounts(p.id)),
    ];
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// 지원자 목록 — 목데이터를 그대로 돌려준다.
class FakeApplicantRepository implements ApplicantRepository {
  FakeApplicantRepository({
    this.applicants,
    this.error,
    this.delay = Duration.zero,
  });

  final List<Applicant>? applicants;
  final Object? error;
  final Duration delay;

  @override
  Future<List<Applicant>> byPosting(int postingId) async {
    if (delay > Duration.zero) await Future<void>.delayed(delay);
    if (error != null) throw error!;

    return applicants ??
        mockApplicants.where((a) => a.jobPostingId == postingId).toList();
  }

  /// 상세 — 목데이터를 조립해 돌려준다. 서버가 한 번에 주는 것과 같은 모양이다
  @override
  Future<ApplicantDetail> detail(int id) async {
    if (delay > Duration.zero) await Future<void>.delayed(delay);
    if (error != null) throw error!;

    final a = (applicants ?? mockApplicants).firstWhere((x) => x.id == id);
    return ApplicantDetail(
      applicant: a,
      stageHistory: mockStageHistory[id] ?? const [],
      evaluations: mockEvaluations[id]?.items ?? const [],
      notes: mockNotes[id] ?? const [],
      files: mockFiles[id] ?? const [],
      avgScore: mockEvaluations[id]?.avgScore,
    );
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
