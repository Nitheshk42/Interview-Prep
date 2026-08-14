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

const KNOWN_SECTIONS = ["resume_sync", "chat", "hybrid", "level", "jd", "general_jd", "tailor"];

function Gated() {
  const { token, profile, refreshProfile } = useAuth();
  const [checked, setChecked] = useState(false);
  const [section, setSection] = useState(DEFAULT_SECTION);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

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
      <Sidebar
        section={section}
        onSectionChange={setSection}
        mobileOpen={mobileNavOpen}
        onMobileClose={() => setMobileNavOpen(false)}
      />
      <div className="flex-1 min-w-0">
        {/* Mobile-only top bar - the hamburger is the only way to reach the sidebar/section nav
            below the `lg` breakpoint, since the sidebar itself is off-canvas until opened. */}
        <div className="lg:hidden flex items-center gap-3 border-b border-gray-200 bg-white px-3 py-2.5 sticky top-0 z-20">
          <button
            type="button"
            onClick={() => setMobileNavOpen(true)}
            aria-label="Open menu"
            className="text-xl leading-none px-1.5 py-1 rounded-lg hover:bg-gray-100 transition"
          >
            ☰
          </button>
          <p className="text-sm font-medium text-gray-900 truncate">StudySager</p>
        </div>
        <main className="flex-1">
          {section === "resume_sync" && <ResumeSyncPage />}
          {section === "chat" && <ChatPage />}
          {section === "hybrid" && <HybridChatPage />}
          {section === "level" && <LevelChatPage />}
          {section === "jd" && <JdChatPage />}
          {section === "general_jd" && <GeneralJdChatPage />}
          {section === "tailor" && <ResumeTailorPage />}
          {!KNOWN_SECTIONS.includes(section) && (
            <div className="p-10 text-gray-400">This section isn't built yet — coming soon.</div>
          )}
        </main>
      </div>
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
