import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import UserMenu from "./components/UserMenu";
import Login from "./pages/Login";
import Register from "./pages/Register";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import VerifyEmail from "./pages/VerifyEmail";
import Terms from "./pages/Terms";
import Privacy from "./pages/Privacy";
import Home from "./pages/Home";
import Me from "./pages/Me";
import CreatorStudio from "./pages/CreatorStudio";
import Settings from "./pages/Settings";
import Scenarios from "./pages/Scenarios";
import ScenarioDetail from "./pages/ScenarioDetail";
import ScenarioRosterDetail from "./pages/ScenarioRosterDetail";
import ScenarioBattle from "./pages/ScenarioBattle";
import ScenarioRecords from "./pages/ScenarioRecords";
import ChallengeRedirect from "./pages/ChallengeRedirect";
import ScenarioComposer from "./pages/ScenarioComposer";
import AdminLayout from "./components/AdminLayout";
import AdminDashboard from "./pages/admin/Dashboard";
import AdminUsers from "./pages/admin/AdminUsers";
import AdminAbilities from "./pages/admin/AdminAbilities";
import AdminTraffic from "./pages/admin/AdminTraffic";
import AdminScenarios from "./pages/admin/AdminScenarios";
import { InkMountains, SealStamp } from "./components/Ornaments";

function RequireAuth({ children }: { children: React.ReactElement }) {
  const { user, initializing } = useAuth();
  // 会话恢复完成前保持当前页（不闪跳登录），避免刷新后被误判为登出
  if (initializing) return null;
  return user ? children : <Navigate to="/login" replace />;
}

function RequireAdmin({ children }: { children: React.ReactElement }) {
  const { user, initializing } = useAuth();
  if (initializing) return null;
  return user?.is_admin ? children : <Navigate to="/" replace />;
}

/** 卷末：远山墨影 + 收卷印。认证页（正门）不落款。 */
function SiteFooter() {
  const { pathname } = useLocation();
  if (pathname === "/login" || pathname === "/register") return null;
  return (
    <footer className="ink-footer" aria-hidden="true">
      <InkMountains className="ink-footer__hills" preserveAspectRatio="none" />
      <span className="ink-footer__seal">
        <SealStamp char="卷" size={26} />
      </span>
    </footer>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <div className="app">
          <UserMenu />
          <div className="eaves" aria-hidden="true" />
          <main className="container">
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="/forgot-password" element={<ForgotPassword />} />
              <Route path="/reset-password" element={<ResetPassword />} />
              <Route path="/verify-email" element={<VerifyEmail />} />
              <Route path="/terms" element={<Terms />} />
              <Route path="/privacy" element={<Privacy />} />
              <Route path="/" element={<Navigate to="/scenarios" replace />} />
              <Route path="/home" element={<RequireAuth><Home /></RequireAuth>} />
              <Route path="/me" element={<RequireAuth><Me /></RequireAuth>} />
              <Route path="/abilities" element={<RequireAuth><CreatorStudio /></RequireAuth>} />
              <Route path="/creator" element={<RequireAuth><CreatorStudio /></RequireAuth>} />
              <Route path="/creator/scenarios/new" element={<RequireAuth><ScenarioComposer /></RequireAuth>} />
              <Route path="/scenarios" element={<RequireAuth><Scenarios /></RequireAuth>} />
              <Route path="/scenarios/:slug" element={<RequireAuth><ScenarioDetail /></RequireAuth>} />
              <Route path="/scenarios/:scenarioSlug/rosters/:rosterId" element={<RequireAuth><ScenarioRosterDetail /></RequireAuth>} />
              <Route path="/scenarios/:scenarioSlug/rosters/:rosterId/battle" element={<RequireAuth><ScenarioBattle /></RequireAuth>} />
              <Route path="/scenarios/:scenarioSlug/rosters/:rosterId/records" element={<RequireAuth><ScenarioRecords /></RequireAuth>} />
              {/* 旧单局归档路由已废弃：兼容跳转到记录阅读页 */}
              <Route path="/scenario-challenges/:id" element={<RequireAuth><ChallengeRedirect /></RequireAuth>} />
              <Route path="/settings" element={<RequireAuth><Settings /></RequireAuth>} />
              <Route path="/admin" element={<RequireAuth><RequireAdmin><AdminLayout /></RequireAdmin></RequireAuth>}>
                <Route index element={<AdminDashboard />} />
                <Route path="users" element={<AdminUsers />} />
                <Route path="abilities" element={<AdminAbilities />} />
                <Route path="traffic" element={<AdminTraffic />} />
                <Route path="scenarios" element={<AdminScenarios />} />
              </Route>
            </Routes>
          </main>
          <SiteFooter />
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
}
