import { Suspense, lazy } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import Layout from './components/Layout'
import { AuthProvider } from './auth/AuthContext'
import { ToastProvider } from './components/Toast'
import { RightPanelProvider } from './components/RightPanel'
import DiveTransition from './components/DiveTransition'
import RequireAuth from './auth/RequireAuth'
import Login from './pages/Login'
import Apply from './pages/Apply'
import Schedule from './pages/Schedule'
import Interview from './pages/Interview'
import Aptitude from './pages/Aptitude'
import Dashboard from './pages/Dashboard'
import Postings from './pages/Postings'
import PostingApplicants from './pages/PostingApplicants'
import Applicants from './pages/Applicants'
import Interviews from './pages/Interviews'
import Evaluations from './pages/Evaluations'
import Settings from './pages/Settings'
import More from './pages/More'
/* three.js 를 초기 번들에서 빼기 위해 이 페이지도 지연 로드한다 (Sidebar 의 ArViewer 와 같은 청크) */
const ArDemo = lazy(() => import('./pages/ArDemo'))

/* 캘린더는 08/31 에 /interviews 에서 /calendar 로 옮겼다. 옛 경로로 들어오면
   쿼리(?slot= 같은 딥링크)를 그대로 달고 새 경로로 보낸다. */
function LegacyCalendarRedirect() {
  const { search } = useLocation()
  return <Navigate to={`/calendar${search}`} replace />
}

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
      {/* 오른쪽 패널은 한 번에 하나 — 아르와 그날 일정이 같은 자리를 쓴다 */}
      <RightPanelProvider>
      {/* 로그인 → 대시보드 접속 시퀀스. 흰빛이 화면 교체를 건너 살아남아야
          하므로 라우트 밖에 둔다 */}
      <DiveTransition>
      <Routes>
        {/* 루트는 대시보드로. 비로그인은 RequireAuth 가 /login 으로 보낸다 */}
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/login" element={<Login />} />
        {/* 공개 지원 폼 (C1). 지원자는 로그인이 없으므로 RequireAuth·Layout 밖이다. */}
        <Route path="/apply/:token" element={<Apply />} />
        {/* 지원자용 면접 일정 선택 — 메일 링크 착지점 (ADR-0016). 마찬가지로 로그인 밖 */}
        <Route path="/schedule/:token" element={<Schedule />} />
        {/* 지원자용 AI 면접 — 메일 링크 착지점. 로그인 밖 */}
        <Route path="/interview/:token" element={<Interview />} />
        {/* 사전 성향 설문 — 메일 링크의 토큰 접근 (ADR-0027) */}
        <Route path="/aptitude/:token" element={<Aptitude />} />
        {/* 아르 3D 모션 검토용. 내비 미노출·데이터 접근 없음 → 로그인 게이트 밖 */}
        <Route
          path="/dev/ar"
          element={
            <Suspense fallback={null}>
              <ArDemo />
            </Suspense>
          }
        />
        <Route element={<RequireAuth />}>
          <Route element={<Layout />}>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/postings" element={<Postings />} />
            <Route path="/postings/:id" element={<PostingApplicants />} />
            <Route path="/applicants" element={<Applicants />} />
            <Route path="/calendar" element={<Interviews />} />
            {/* 옛 경로. 북마크·메일 링크가 깨지지 않게 남긴다 */}
            <Route path="/interviews" element={<LegacyCalendarRedirect />} />
            <Route path="/evaluations" element={<Evaluations />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/more" element={<More />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
      </DiveTransition>
      </RightPanelProvider>
      </ToastProvider>
    </AuthProvider>
  )
}
