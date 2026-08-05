import { useAuth } from "@clerk/clerk-react";
import { Routes, Route, Navigate } from "react-router-dom";
import { useEffect } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { setTokenProvider } from "./api/client";
import LandingPage from "./pages/LandingPage";
import AppPage from "./pages/AppPage";
import SettingsPage from "./pages/SettingsPage";

gsap.registerPlugin(ScrollTrigger);

function ProtectedRoute({ children }) {
  const { isSignedIn, isLoaded } = useAuth();
  if (!isLoaded) {
    return (
      <div className="min-h-screen bg-base-100 flex items-center justify-center">
        <span className="loading loading-dots loading-lg" />
      </div>
    );
  }
  if (!isSignedIn) {
    return <Navigate to="/" replace />;
  }
  return children;
}

export default function App() {
  const { getToken } = useAuth();

  useEffect(() => {
    setTokenProvider(getToken);
  }, [getToken]);

  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route
        path="/app"
        element={
          <ProtectedRoute>
            <AppPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/settings"
        element={
          <ProtectedRoute>
            <SettingsPage />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
