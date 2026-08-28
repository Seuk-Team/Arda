import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import { AuthProvider } from './auth/AuthContext'
import { ToastProvider } from './components/Toast'
import RequireAuth from './auth/RequireAuth'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Postings from './pages/Postings'
import PostingApplicants from './pages/PostingApplicants'
import Applicants from './pages/Applicants'
import Interviews from './pages/Interviews'
import Evaluations from './pages/Evaluations'
import Settings from './pages/Settings'

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
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
