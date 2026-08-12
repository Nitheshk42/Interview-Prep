import { useEffect, useState } from "react";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ProviderProvider } from "./context/ProviderContext";
import AuthPage from "./pages/AuthPage";
import OnboardingPage from "./pages/OnboardingPage";
import ChatPage from "./pages/ChatPage";
import HybridChatPage from "./pages/HybridChatPage";
import LevelChatPage from "./pages/LevelChatPage";
import JdChatPage from "./pages/JdChatPage";
import GeneralJdChatPage from "./pages/GeneralJdChatPage";
import ResumeTailorPage from "./pages/ResumeTailorPage";
import ResumeSyncPage from "./pages/ResumeSyncPage";
import Sidebar from "./components/Sidebar";
import { DEFAULT_SECTION } from "./sections";

function Gated() {
  const { token, profile, refreshProfile } = useAuth();
  const [checked, setChecked] = useState(false);
  const [section, setSection] = useState(DEFAULT_SECTION);

  useEffect(() => {
    if (token && profile === null) {
      refreshProfile().finally(() => setChecked(true));
    } else {
      setChecked(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  if (!token) return <AuthPage />;
  if (!checked) return <div className="min-h-screen flex items-center justify-center text-gray-400">Loading...</div>;
  if (!profile?.resume_uploaded) return <OnboardingPage onDone={() => setSection(DEFAULT_SECTION)} />;

  return (
    <div className="flex">
      <Sidebar section={section} onSectionChange={setSection} />
      <main className="flex-1">
        {section === "resume_sync" && <ResumeSyncPage />}
        {section === "chat" && <ChatPage />}
        {section === "hybrid" && <HybridChatPage />}
        {section === "level" && <LevelChatPage />}
        {section === "jd" && <JdChatPage />}
        {section === "general_jd" && <GeneralJdChatPage />}
        {section === "tailor" && <ResumeTailorPage />}
        {!["resume_sync", "chat", "hybrid", "level", "jd", "general_jd", "tailor"].includes(section) && (
          <div className="p-10 text-gray-400">This section isn't built yet — coming soon.</div>
        )}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <ProviderProvider>
        <Gated />
      </ProviderProvider>
    </AuthProvider>
  );
}
