import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import Navbar from "./components/Navbar";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Home from "./pages/Home";
import CreatorStudio from "./pages/CreatorStudio";
import BattleReport from "./pages/BattleReport";
import Books from "./pages/Books";
import Friends from "./pages/Friends";
import Leaderboard from "./pages/Leaderboard";
import Share from "./pages/Share";
import Settings from "./pages/Settings";
import Scenarios from "./pages/Scenarios";
import ScenarioDetail from "./pages/ScenarioDetail";
import ScenarioChallenge from "./pages/ScenarioChallenge";
import ScenarioRosterDetail from "./pages/ScenarioRosterDetail";
import ScenarioComposer from "./pages/ScenarioComposer";
import ScenarioEditor from "./pages/ScenarioEditor";
import AdminLayout from "./components/AdminLayout";
import AdminDashboard from "./pages/admin/Dashboard";
import AdminUsers from "./pages/admin/AdminUsers";
import AdminAbilities from "./pages/admin/AdminAbilities";
import AdminBattles from "./pages/admin/AdminBattles";
import AdminRelations from "./pages/admin/AdminRelations";
import AdminTraffic from "./pages/admin/AdminTraffic";
import TestArena from "./pages/admin/TestArena";
import CoreGuessLab from "./pages/admin/CoreGuessLab";
import BattleChain from "./pages/admin/BattleChain";
import LoadoutBrowser from "./pages/admin/LoadoutBrowser";
import LoadoutDetail from "./pages/admin/LoadoutDetail";
import AdminBattleDetail from "./pages/admin/AdminBattleDetail";
import PromptSchemes from "./pages/admin/PromptSchemes";
import AdminScenarios from "./pages/admin/AdminScenarios";

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

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Navbar />
        <div className="eaves" aria-hidden="true" />
        <main className="container">
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/share/:token" element={<Share />} />
            <Route path="/" element={<RequireAuth><Home /></RequireAuth>} />
            <Route path="/abilities" element={<RequireAuth><CreatorStudio /></RequireAuth>} />
            <Route path="/creator" element={<RequireAuth><CreatorStudio /></RequireAuth>} />
            <Route path="/creator/scenarios/new" element={<RequireAuth><ScenarioComposer /></RequireAuth>} />
            <Route path="/creator/scenarios/:id" element={<RequireAuth><ScenarioEditor /></RequireAuth>} />
            <Route path="/books" element={<RequireAuth><Books /></RequireAuth>} />
            <Route path="/battles/:id" element={<RequireAuth><BattleReport /></RequireAuth>} />
            <Route path="/leaderboard" element={<RequireAuth><Leaderboard /></RequireAuth>} />
            <Route path="/scenarios" element={<RequireAuth><Scenarios /></RequireAuth>} />
            <Route path="/scenarios/:id" element={<RequireAuth><ScenarioDetail /></RequireAuth>} />
            <Route path="/scenarios/:scenarioId/rosters/:rosterId" element={<RequireAuth><ScenarioRosterDetail /></RequireAuth>} />
            <Route path="/scenario-challenges/:id" element={<RequireAuth><ScenarioChallenge /></RequireAuth>} />
            <Route path="/friends" element={<RequireAuth><Friends /></RequireAuth>} />
            <Route path="/settings" element={<RequireAuth><Settings /></RequireAuth>} />
            <Route path="/admin" element={<RequireAuth><RequireAdmin><AdminLayout /></RequireAdmin></RequireAuth>}>
              <Route index element={<AdminDashboard />} />
              <Route path="users" element={<AdminUsers />} />
              <Route path="abilities" element={<AdminAbilities />} />
              <Route path="battles" element={<AdminBattles />} />
              <Route path="loadouts" element={<LoadoutBrowser />} />
              <Route path="loadouts/:id" element={<LoadoutDetail />} />
              <Route path="battles/:id" element={<AdminBattleDetail />} />
              <Route path="relations" element={<AdminRelations />} />
              <Route path="traffic" element={<AdminTraffic />} />
              <Route path="chain" element={<BattleChain />} />
              <Route path="prompt-schemes" element={<PromptSchemes />} />
              <Route path="scenarios" element={<AdminScenarios />} />
              <Route path="test" element={<TestArena />} />
              <Route path="test/core-guess" element={<CoreGuessLab />} />
            </Route>
          </Routes>
        </main>
      </BrowserRouter>
    </AuthProvider>
  );
}
