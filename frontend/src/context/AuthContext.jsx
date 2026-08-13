import { createContext, useContext, useState, useCallback, useEffect, useRef } from "react";
import * as api from "../api/client";

const AuthContext = createContext(null);

// Security behavior, both deliberate:
// 1. sessionStorage instead of localStorage - sessionStorage is cleared when the tab/browser is
//    actually closed (localStorage survives indefinitely), so closing the tab and reopening the
//    site requires logging in again, instead of silently picking back up where you left off.
// 2. Idle timeout - if there's no mouse/keyboard/touch activity for 5 minutes while a tab stays
//    open, log out automatically rather than leaving an authenticated session sitting open on an
//    unattended screen.
const IDLE_TIMEOUT_MS = 5 * 60 * 1000;
const ACTIVITY_EVENTS = ["mousedown", "mousemove", "keydown", "scroll", "touchstart"];

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => sessionStorage.getItem("studysager_token"));
  const [username, setUsername] = useState(() => sessionStorage.getItem("studysager_username"));
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(false);
  const idleTimerRef = useRef(null);

  const applyAuth = useCallback((data) => {
    sessionStorage.setItem("studysager_token", data.access_token);
    sessionStorage.setItem("studysager_username", data.username);
    setToken(data.access_token);
    setUsername(data.username);
    setProfile(data.profile);
  }, []);

  const doSignup = useCallback(async (u, e, p) => {
    setLoading(true);
    try {
      const data = await api.signup(u, e, p);
      applyAuth(data);
    } finally {
      setLoading(false);
    }
  }, [applyAuth]);

  const doLogin = useCallback(async (u, p) => {
    setLoading(true);
    try {
      const data = await api.login(u, p);
      applyAuth(data);
    } finally {
      setLoading(false);
    }
  }, [applyAuth]);

  const refreshProfile = useCallback(async () => {
    const data = await api.me();
    setProfile(data.profile);
    return data.profile;
  }, []);

  const logout = useCallback(() => {
    sessionStorage.removeItem("studysager_token");
    sessionStorage.removeItem("studysager_username");
    setToken(null);
    setUsername(null);
    setProfile(null);
  }, []);

  // Idle timeout: only runs while logged in. Any activity event resets the 5-minute clock; if
  // it ever fires uninterrupted, log out.
  useEffect(() => {
    if (!token) return;

    function resetTimer() {
      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
      idleTimerRef.current = setTimeout(() => {
        logout();
      }, IDLE_TIMEOUT_MS);
    }

    resetTimer();
    ACTIVITY_EVENTS.forEach((evt) => document.addEventListener(evt, resetTimer));

    return () => {
      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
      ACTIVITY_EVENTS.forEach((evt) => document.removeEventListener(evt, resetTimer));
    };
  }, [token, logout]);

  return (
    <AuthContext.Provider
      value={{ token, username, profile, loading, doSignup, doLogin, logout, refreshProfile, setProfile }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
