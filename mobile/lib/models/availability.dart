/// 면접 가능 시간 한 구간 — 설정 `면접 가능 시간` 탭 (큐 8 4단계, 2026-09-03).
///
/// 담당자가 등록해 두면 일정 제안이 이 안에서 후보 슬롯을 고른다(ADR-0016).
/// 앱은 읽기만 한다 — 등록은 시간 구간을 고르는 UI 가 따로 필요하다.
library;

class Availability {
  const Availability({
    required this.id,
    required this.startAt,
    required this.endAt,
  });

  final int id;
  final DateTime startAt;
  final DateTime endAt;
}

/// 서버 응답 → 모델. `AvailabilityOut`(backend/app/schemas/availability.py).
extension AvailabilityJson on Availability {
  static Availability fromJson(Map<String, dynamic> json) => Availability(
    id: json['id'] as int,
    // 서버는 UTC 로 준다 — toLocal() 을 빼면 9시간 어긋난 시각이 뜬다
    startAt: DateTime.parse(json['start_at'] as String).toLocal(),
    endAt: DateTime.parse(json['end_at'] as String).toLocal(),
  );
}
