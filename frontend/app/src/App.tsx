import { Suspense, lazy } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import { AuthProvider } from './auth/AuthContext'
import { ToastProvider } from './components/Toast'
import RequireAuth from './auth/RequireAuth'
import Login from './pages/Login'
import Apply from './pages/Apply'
import Schedule from './pages/Schedule'
import Dashboard from './pages/Dashboard'
import Postings from './pages/Postings'
import PostingApplicants from './pages/PostingApplicants'
import Applicants from './pages/Applicants'
import Interviews from './pages/Interviews'
import Evaluations from './pages/Evaluations'
import Settings from './pages/Settings'
/* three.js 를 초기 번들에서 빼기 위해 이 페이지도 지연 로드한다 (Sidebar 의 ArViewer 와 같은 청크) */
const ArDemo = lazy(() => import('./pages/ArDemo'))

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
      <Routes>
        {/* 루트는 대시보드로. 비로그인은 RequireAuth 가 /login 으로 보낸다 */}
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/login" element={<Login />} />
        {/* 공개 지원 폼 (C1). 지원자는 로그인이 없으므로 RequireAuth·Layout 밖이다. */}
        <Route path="/apply/:token" element={<Apply />} />
        {/* 지원자용 면접 일정 선택 — 메일 링크 착지점 (ADR-0016). 마찬가지로 로그인 밖 */}
        <Route path="/schedule/:token" element={<Schedule />} />
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
            <Route path="/interviews" element={<Interviews />} />
            <Route path="/evaluations" element={<Evaluations />} />
            <Route path="/settings" element={<Settings />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
      </ToastProvider>
    </AuthProvider>
  )
}
