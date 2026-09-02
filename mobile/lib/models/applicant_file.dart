/// 지원자가 낸 첨부 파일 — 01-erd `files` 테이블 · 웹 `FileOut` 과 같은 모양.
///
/// 지원자는 이력서·자기소개서 2종을 낸다. 업로드는 지원 폼(웹 전용)에서
/// presigned URL 로 S3 직행이고, 앱은 **보는 쪽만** 한다.
///
/// 다운로드는 `POST /files/{id}/presign-download` 로 받은 URL 로 이동한다 —
/// 웹이 fetch 로 받다가 CORS(PUT only)에 막혀 링크 이동으로 바꿨다(C7).
/// 앱은 그 URL 을 브라우저로 넘긴다. 실제 연동은 큐 8이다.
library;

class ApplicantFile {
  const ApplicantFile({
    required this.id,
    required this.applicationId,
    required this.filename,
    required this.kind,
    required this.sizeBytes,
    required this.contentType,
    required this.createdAt,
  });

  /// `files.id`
  final int id;

  /// `files.application_id`
  final int applicationId;

  /// `files.filename` — 지원자가 올린 원본 이름
  final String filename;

  /// `files.kind` — `resume` / `cover_letter`
  final FileKind kind;

  /// `files.size_bytes`
  final int sizeBytes;

  /// `files.content_type`
  final String contentType;

  /// `files.created_at`
  final DateTime createdAt;

  /// "240 KB" — 웹 `fmtBytes` 와 같은 규칙.
  /// 1KB 미만은 바이트, 1MB 미만은 정수 KB, 그 위는 소수 첫째 자리 MB.
  String get sizeLabel {
    if (sizeBytes < 1024) return '$sizeBytes B';
    if (sizeBytes < 1024 * 1024) return '${(sizeBytes / 1024).round()} KB';
    return '${(sizeBytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }
}

/// 웹 `KIND_LABEL` 과 같은 문구. 모르는 값이 오면 코드를 그대로 보여 준다 —
/// 웹도 `KIND_LABEL[f.kind] ?? f.kind` 로 같게 처리한다.
enum FileKind {
  resume('resume', '이력서'),
  coverLetter('cover_letter', '자기소개서 파일');

  const FileKind(this.value, this.label);

  final String value;
  final String label;

  static String labelFor(String value) {
    for (final k in FileKind.values) {
      if (k.value == value) return k.label;
    }
    return value;
  }
}

/// 서버 응답 → 모델. `FileOut`.
/// `s3_key` 는 오지 않는다 — 다운로드는 presigned URL 로 따로 발급한다.
extension ApplicantFileJson on ApplicantFile {
  static ApplicantFile fromJson(
    Map<String, dynamic> json, {
    required int applicationId,
  }) => ApplicantFile(
    id: json['id'] as int,
    applicationId: applicationId,
    filename: json['filename'] as String,
    kind: FileKind.values.firstWhere(
      (k) => k.value == json['kind'],
      // 모르는 종류면 이력서로 넘겨짚지 않는다 — 자기소개서가 이력서로 보이면
      // 담당자가 다른 파일을 열게 된다
      orElse: () => FileKind.coverLetter,
    ),
    sizeBytes: json['size_bytes'] as int? ?? 0,
    contentType: json['content_type'] as String? ?? '',
    createdAt: DateTime.parse(json['created_at'] as String),
  );
}
