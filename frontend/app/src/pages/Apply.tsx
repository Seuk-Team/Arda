import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import styles from './Apply.module.css'

/* 공개 지원 폼 (C1). 로그인 없이 토큰 링크로 들어온다 — 그래서 Layout·RequireAuth
   밖에 있고, 우리 서버 호출에는 전부 auth: false 를 준다.
   화면 기준은 frontend/mockups/mockup-apply.html. */

interface PostingPublic {
  id: number
  title: string
  description: string | null
}

interface PresignOut {
  upload_url: string
  s3_key: string
}

type FileKind = 'resume' | 'cover_letter'

interface SubmittedFile {
  s3_key: string
  filename: string
  size_bytes: number
  content_type: string
  kind: FileKind
}

/* 로드 결과를 문자열 하나로 뭉개지 않는다 — 410(마감)과 404(잘못된 링크)는
   지원자가 해야 할 행동이 다르다. 마감은 포기해도 되고, 404 는 링크를 다시 봐야 한다. */
type Load =
  | { kind: 'loading' }
  | { kind: 'ok'; posting: PostingPublic }
  | { kind: 'closed' }
  | { kind: 'missing' }
  | { kind: 'error'; message: string }

const MAX_BYTES = 10 * 1024 * 1024
const ALLOWED_EXT = ['pdf', 'docx', 'hwp', 'hwpx']

/* 확장자별 content_type. 브라우저가 file.type 을 비워 주는 경우가 있는데(특히 hwp),
   서버는 확장자와 타입이 맞는지 본다(F3). 빈 값을 그대로 보내면 거기서 막힌다. */
const TYPE_BY_EXT: Record<string, string> = {
  pdf: 'application/pdf',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  hwp: 'application/octet-stream',
  hwpx: 'application/octet-stream',
}

function extOf(filename: string) {
  return filename.split('.').pop()?.toLowerCase() ?? ''
}

function contentTypeOf(file: File) {
  const ext = extOf(file.name)
  // hwp 는 OS·브라우저마다 타입이 제각각이라 서버가 octet-stream 까지 받는다. 거기 맞춘다.
  if (ext === 'hwp' || ext === 'hwpx') return TYPE_BY_EXT[ext]
  return file.type || TYPE_BY_EXT[ext] || ''
}

/* 서버도 같은 것을 보지만(F3) 여기서 먼저 본다 — 10MB 를 다 올린 뒤에 거절당하면
   지원자는 업로드 시간을 통째로 버린다. */
function checkFile(file: File): string | null {
  if (!ALLOWED_EXT.includes(extOf(file.name))) {
    return 'PDF · DOCX · HWP 파일만 올릴 수 있습니다'
  }
  if (file.size > MAX_BYTES) return '파일은 10MB 이하만 올릴 수 있습니다'
  if (file.size === 0) return '빈 파일입니다'
  return null
}

async function upload(file: File, kind: FileKind): Promise<SubmittedFile> {
  const contentType = contentTypeOf(file)
  const presign = await api.post<PresignOut>(
    '/public/files/presign-upload',
    { filename: file.name, content_type: contentType, kind, size_bytes: file.size },
    { auth: false },
  )

  /* S3 직행이라 여기만 api 클라이언트를 쓰지 않는다 — 우리 서버가 아니다.
     서명에 들어간 Content-Type 과 다르게 올리면 S3 가 거부한다. */
  const put = await fetch(presign.upload_url, {
    method: 'PUT',
    headers: { 'Content-Type': contentType },
    body: file,
  })
  if (!put.ok) throw new Error(`파일을 올리지 못했습니다 (${put.status})`)

  return {
    s3_key: presign.s3_key,
    filename: file.name,
    size_bytes: file.size,
    content_type: contentType,
    kind,
  }
}

export default function Apply() {
  const { token = '' } = useParams()
  const [load, setLoad] = useState<Load>({ kind: 'loading' })

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [education, setEducation] = useState('')
  const [careerYears, setCareerYears] = useState('')
  const [selfIntro, setSelfIntro] = useState('')
  const [resume, setResume] = useState<File | null>(null)
  const [coverLetter, setCoverLetter] = useState<File | null>(null)
  const [agreed, setAgreed] = useState(false)

  const [pending, setPending] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    api
      .get<PostingPublic>(`/public/postings/by-token/${encodeURIComponent(token)}`, {
        auth: false,
      })
      .then((posting) => {
        if (alive) setLoad({ kind: 'ok', posting })
      })
      .catch((err) => {
        if (!alive) return
        if (err instanceof ApiError && err.code === 'GONE') {
          setLoad({ kind: 'closed' })
        } else if (err instanceof ApiError && err.status === 404) {
          setLoad({ kind: 'missing' })
        } else {
          setLoad({
            kind: 'error',
            message: err instanceof ApiError ? err.message : '공고를 불러오지 못했습니다',
          })
        }
      })
    return () => {
      alive = false
    }
  }, [token])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (load.kind !== 'ok') return
    setError(null)

    for (const file of [resume, coverLetter]) {
      const problem = file ? checkFile(file) : null
      if (problem) {
        setError(problem)
        return
      }
    }

    setPending(true)
    try {
      const files: SubmittedFile[] = []
      if (resume) files.push(await upload(resume, 'resume'))
      if (coverLetter) files.push(await upload(coverLetter, 'cover_letter'))

      await api.post(
        `/public/postings/${load.posting.id}/applications`,
        {
          name: name.trim(),
          email: email.trim(),
          phone: phone.trim(),
          education: education.trim() || null,
          career_years: careerYears === '' ? null : Number(careerYears),
          self_intro: selfIntro.trim() || null,
          privacy_agreed: true,
          files,
        },
        { auth: false },
      )
      setDone(true)
    } catch (err) {
      if (err instanceof ApiError && err.code === 'CONFLICT') {
        setError('이미 이 공고에 지원하셨습니다. 같은 이메일로는 한 번만 지원할 수 있습니다.')
      } else if (err instanceof ApiError && err.code === 'GONE') {
        setError('접수하는 사이 공고가 마감되었습니다.')
      } else if (err instanceof ApiError) {
        setError(err.message)
      } else {
        setError(err instanceof Error ? err.message : '제출하지 못했습니다')
      }
      setPending(false)
    }
  }

  if (load.kind === 'loading') {
    return (
      <Shell>
        <p className={styles.notice}>공고를 불러오는 중입니다…</p>
      </Shell>
    )
  }

  if (load.kind === 'closed' || load.kind === 'missing' || load.kind === 'error') {
    const message =
      load.kind === 'closed'
        ? '이 공고는 마감되었습니다. 다음 채용에서 다시 뵙기를 바랍니다.'
        : load.kind === 'missing'
          ? '잘못된 링크입니다. 안내 메일의 주소를 다시 확인해 주세요.'
          : load.message
    return (
      <Shell>
        <p className={styles.notice} role="alert">
          {message}
        </p>
      </Shell>
    )
  }

  if (done) {
    return (
      <Shell title={load.posting.title}>
        <p className={styles.notice}>
          지원서가 접수되었습니다. 입력하신 이메일로 접수 확인 메일을 보내드립니다.
          <br />
          서류 검토 결과는 전형 일정에 따라 순차적으로 안내드립니다.
        </p>
      </Shell>
    )
  }

  const ready = name.trim() !== '' && email.trim() !== '' && phone.trim() !== '' && agreed

  return (
    <Shell title={load.posting.title}>
      {load.posting.description && <p className={styles.desc}>{load.posting.description}</p>}

      <form className={styles.form} onSubmit={handleSubmit} noValidate>
        <Field label="이름" value={name} onChange={setName} autoComplete="name" placeholder="홍길동" disabled={pending} />
        <Field label="이메일" value={email} onChange={setEmail} type="email" autoComplete="email" placeholder="name@example.com" disabled={pending} />
        <Field label="연락처" value={phone} onChange={setPhone} type="tel" autoComplete="tel" placeholder="010-0000-0000" disabled={pending} />
        <Field label="최종 학력" value={education} onChange={setEducation} placeholder="OO대학교 컴퓨터공학과" disabled={pending} />
        <Field label="경력 연차" value={careerYears} onChange={setCareerYears} type="number" placeholder="신입이면 0" disabled={pending} />

        <label className={styles.label}>
          자기소개서
          <textarea
            className={styles.textarea}
            rows={6}
            value={selfIntro}
            onChange={(e) => setSelfIntro(e.target.value)}
            placeholder="자기소개서를 입력해 주세요"
            disabled={pending}
          />
        </label>

        <FilePick label="이력서" file={resume} onPick={setResume} disabled={pending} />
        <FilePick label="자기소개서 파일" file={coverLetter} onPick={setCoverLetter} disabled={pending} />
        <p className={styles.hint}>PDF · DOCX · HWP · 10MB 이하</p>

        <label className={styles.agree}>
          <input
            type="checkbox"
            checked={agreed}
            onChange={(e) => setAgreed(e.target.checked)}
            disabled={pending}
          />
          <span>
            개인정보 수집·이용에 동의합니다.
            <span className={styles.req}>동의하지 않으면 제출할 수 없습니다.</span>
          </span>
        </label>

        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}

        <button type="submit" className="btn btn-primary" disabled={!ready || pending}>
          {pending ? '제출 중…' : '지원서 제출'}
        </button>
      </form>
    </Shell>
  )
}

function Shell({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.head}>
          <span className={styles.logo}>
            <span className={styles.seed}>A</span>rda
          </span>
          {title && <h1 className={styles.title}>{title}</h1>}
        </div>
        {children}
      </div>
    </div>
  )
}

interface FieldProps {
  label: string
  value: string
  onChange: (v: string) => void
  type?: string
  placeholder?: string
  autoComplete?: string
  disabled?: boolean
}

function Field({ label, value, onChange, type = 'text', ...rest }: FieldProps) {
  return (
    <label className={styles.label}>
      {label}
      <input
        className={styles.input}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        {...rest}
      />
    </label>
  )
}

function FilePick({
  label,
  file,
  onPick,
  disabled,
}: {
  label: string
  file: File | null
  onPick: (f: File | null) => void
  disabled?: boolean
}) {
  return (
    <label className={styles.label}>
      {label}
      <span className={styles.upload}>
        <span className={file ? styles.fileName : styles.fileEmpty}>
          {file ? file.name : '선택된 파일 없음'}
        </span>
        <input
          className={styles.fileInput}
          type="file"
          accept=".pdf,.docx,.hwp,.hwpx"
          onChange={(e) => onPick(e.target.files?.[0] ?? null)}
          disabled={disabled}
        />
      </span>
    </label>
  )
}
