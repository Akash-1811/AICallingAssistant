import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { GuestRoute, ProtectedRoute } from "./auth/AuthContext";
import { AppLayout } from "./AppLayout";
import { CallReviewPage } from "./pages/CallReviewPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LiveCallsPage } from "./pages/LiveCallsPage";
import { KnowledgeBasePage } from "./pages/KnowledgeBasePage";
import { LoginPage } from "./pages/LoginPage";
import { SignupPage } from "./pages/SignupPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<GuestRoute />}>
          <Route path="login" element={<LoginPage />} />
          <Route path="signup" element={<SignupPage />} />
        </Route>
        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            <Route index element={<DashboardPage />} />
            <Route path="dashboard" element={<Navigate to="/" replace />} />
            <Route path="live" element={<LiveCallsPage />} />
            <Route path="knowledge" element={<KnowledgeBasePage />} />
            <Route path="analytics" element={<AnalyticsPage />} />
            <Route path="conversations/:id" element={<CallReviewPage />} />
          </Route>
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
