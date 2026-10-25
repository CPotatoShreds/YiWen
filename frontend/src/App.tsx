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
import Yiwenlu from "./pages/Yiwenlu";
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

/** 会话恢复中的占位。不可 return null —— 那会让刷新后出现一瞬白屏。 */
function AppLoading() {
  return (
    <div className="app-loading" role="status" aria-busy="true" aria-label="载入中">
      <span className="skeleton app-loading__bar" />
    </div>
  );
}

function RequireAuth({ children }: { children: React.ReactElement }) {
  const { user, initializing } = useAuth();
  const location = useLocation();
  if (initializing) return <AppLoading />;
  // 记住来处：深链（分享、书签）不能被「请先登录」这一跳吃掉
  return user ? children : <Navigate to="/login" replace state={{ from: location }} />;
}

function RequireAdmin({ children }: { children: React.ReactElement }) {
  const { user, initializing } = useAuth();
  if (initializing) return <AppLoading />;
  // 未登录的情况由外层 RequireAuth 拦下并带上 returnTo，这里只处理「已登录但非管理员」
  return user?.is_admin ? children : <Navigate to="/home" replace />;
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
              <Route path="/" element={<Navigate to="/home" replace />} />
              <Route path="/home" element={<RequireAuth><Home /></RequireAuth>} />
              <Route path="/me" element={<RequireAuth><Me /></RequireAuth>} />
              <Route path="/yiwenlu" element={<RequireAuth><Yiwenlu /></RequireAuth>} />
              <Route path="/yiwenlu/characters/:id" element={<RequireAuth><Yiwenlu kind="character" /></RequireAuth>} />
              <Route path="/yiwenlu/abilities/:id" element={<RequireAuth><Yiwenlu kind="ability" /></RequireAuth>} />
              {/* 旧地址兼容重定向 */}
              <Route path="/abilities" element={<Navigate to="/yiwenlu" replace />} />
              <Route path="/creator" element={<Navigate to="/yiwenlu" replace />} />
              <Route path="/scenarios" element={<RequireAuth><Scenarios /></RequireAuth>} />
              <Route path="/scenarios/:slug" element={<RequireAuth><ScenarioDetail /></RequireAuth>} />
              {/* 立异闻：与 /rosters/:rosterId 同枝。v7 静态段优先于动态段，故 new 不会被当成 rosterId */}
              <Route path="/scenarios/:slug/rosters/new" element={<RequireAuth><ScenarioComposer /></RequireAuth>} />
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
