import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import AppFrame from "./components/AppFrame";
import { ConfirmProvider } from "./components/ConfirmProvider";
const Login = lazy(() => import("./pages/Login"));
const Register = lazy(() => import("./pages/Register"));
const ForgotPassword = lazy(() => import("./pages/ForgotPassword"));
const ResetPassword = lazy(() => import("./pages/ResetPassword"));
const VerifyEmail = lazy(() => import("./pages/VerifyEmail"));
const Terms = lazy(() => import("./pages/Terms"));
const Privacy = lazy(() => import("./pages/Privacy"));
const Home = lazy(() => import("./pages/Home"));
const Me = lazy(() => import("./pages/Me"));
const Yiwenlu = lazy(() => import("./pages/Yiwenlu"));
const Settings = lazy(() => import("./pages/Settings"));
const Scenarios = lazy(() => import("./pages/Scenarios"));
const ScenarioDetail = lazy(() => import("./pages/ScenarioDetail"));
const ScenarioRosterDetail = lazy(() => import("./pages/ScenarioRosterDetail"));
const ScenarioBattle = lazy(() => import("./pages/ScenarioBattle"));
const ScenarioRecords = lazy(() => import("./pages/ScenarioRecords"));
const ChallengeRedirect = lazy(() => import("./pages/ChallengeRedirect"));
const ScenarioComposer = lazy(() => import("./pages/ScenarioComposer"));
import AdminLayout from "./components/AdminLayout";
const AdminDashboard = lazy(() => import("./pages/admin/Dashboard"));
const AdminUsers = lazy(() => import("./pages/admin/AdminUsers"));
const AdminAbilities = lazy(() => import("./pages/admin/AdminAbilities"));
const AdminTraffic = lazy(() => import("./pages/admin/AdminTraffic"));
const AdminScenarios = lazy(() => import("./pages/admin/AdminScenarios"));
const AdminScenarioNew = lazy(() => import("./pages/admin/AdminScenarioNew"));

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

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <ConfirmProvider>
        <AppFrame>
          <Suspense fallback={<AppLoading />}>
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
              {/* 刻印奇人：与 /rosters/:rosterId 同枝。v7 静态段优先于动态段，故 new 不会被当成 rosterId */}
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
                {/* 立卷：静态段优先于任何动态段，与 /scenarios/:slug/rosters/new 同一条规矩 */}
                <Route path="scenarios/new" element={<AdminScenarioNew />} />
              </Route>
            </Routes>
          </Suspense>
        </AppFrame>
        </ConfirmProvider>
      </BrowserRouter>
    </AuthProvider>
  );
}
