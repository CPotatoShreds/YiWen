import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import Navbar from "./components/Navbar";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Home from "./pages/Home";
import MyAbilities from "./pages/MyAbilities";
import BattleReport from "./pages/BattleReport";
import Books from "./pages/Books";
import Friends from "./pages/Friends";
import Leaderboard from "./pages/Leaderboard";
import Share from "./pages/Share";
import Settings from "./pages/Settings";
import AdminLayout from "./components/AdminLayout";
import AdminDashboard from "./pages/admin/Dashboard";
import AdminUsers from "./pages/admin/AdminUsers";
import AdminAbilities from "./pages/admin/AdminAbilities";
import AdminBattles from "./pages/admin/AdminBattles";
import AdminRelations from "./pages/admin/AdminRelations";
import AdminTraffic from "./pages/admin/AdminTraffic";
import TestArena from "./pages/admin/TestArena";

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
            <Route path="/abilities" element={<RequireAuth><MyAbilities /></RequireAuth>} />
            <Route path="/books" element={<RequireAuth><Books /></RequireAuth>} />
            <Route path="/battles/:id" element={<RequireAuth><BattleReport /></RequireAuth>} />
            <Route path="/leaderboard" element={<RequireAuth><Leaderboard /></RequireAuth>} />
            <Route path="/friends" element={<RequireAuth><Friends /></RequireAuth>} />
            <Route path="/settings" element={<RequireAuth><Settings /></RequireAuth>} />
            <Route path="/admin" element={<RequireAuth><RequireAdmin><AdminLayout /></RequireAdmin></RequireAuth>}>
              <Route index element={<AdminDashboard />} />
              <Route path="users" element={<AdminUsers />} />
              <Route path="abilities" element={<AdminAbilities />} />
              <Route path="battles" element={<AdminBattles />} />
              <Route path="relations" element={<AdminRelations />} />
              <Route path="traffic" element={<AdminTraffic />} />
              <Route path="test" element={<TestArena />} />
            </Route>
          </Routes>
        </main>
      </BrowserRouter>
    </AuthProvider>
  );
}
