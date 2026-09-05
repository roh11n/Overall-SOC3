import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "@/contexts/AuthContext";
import { ThemeProvider, useTheme } from "@/contexts/ThemeContext";
import { TenantProvider } from "@/contexts/TenantContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import Layout from "@/components/Layout";
import LoginPage from "@/pages/LoginPage";
import ExecutiveOverview from "@/pages/ExecutiveOverview";
import SocManagerDashboard from "@/pages/SocManagerDashboard";
import ClientDashboard from "@/pages/ClientDashboard";
import DetectionEngineeringDashboard from "@/pages/DetectionEngineeringDashboard";
import ThreatIntelDashboard from "@/pages/ThreatIntelDashboard";
import SoarAutomationDashboard from "@/pages/SoarAutomationDashboard";
import ComparisonDashboard from "@/pages/ComparisonDashboard";
import SettingsPage from "@/pages/SettingsPage";

function ThemedToaster() {
  const { theme } = useTheme();
  return <Toaster position="bottom-right" theme={theme} richColors closeButton duration={3500} />;
}

function App() {
  return (
    <div className="App">
      <ThemeProvider>
        <BrowserRouter>
          <AuthProvider>
            <TenantProvider>
              <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route path="/" element={<ProtectedRoute><Layout><ExecutiveOverview /></Layout></ProtectedRoute>} />
                <Route path="/soc-manager" element={<ProtectedRoute><Layout><SocManagerDashboard /></Layout></ProtectedRoute>} />
                <Route path="/client" element={<ProtectedRoute><Layout><ClientDashboard /></Layout></ProtectedRoute>} />
                <Route path="/detection" element={<ProtectedRoute><Layout><DetectionEngineeringDashboard /></Layout></ProtectedRoute>} />
                <Route path="/threat-intel" element={<ProtectedRoute><Layout><ThreatIntelDashboard /></Layout></ProtectedRoute>} />
                <Route path="/soar" element={<ProtectedRoute><Layout><SoarAutomationDashboard /></Layout></ProtectedRoute>} />
                <Route path="/comparison" element={<ProtectedRoute><Layout><ComparisonDashboard /></Layout></ProtectedRoute>} />
                <Route path="/settings" element={<ProtectedRoute><Layout><SettingsPage /></Layout></ProtectedRoute>} />
              </Routes>
            </TenantProvider>
          </AuthProvider>
        </BrowserRouter>
        <ThemedToaster />
      </ThemeProvider>
    </div>
  );
}

export default App;
