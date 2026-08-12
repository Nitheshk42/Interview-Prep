import { createContext, useContext, useState, useCallback } from "react";
import * as api from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem("studysager_token"));
  const [username, setUsername] = useState(() => localStorage.getItem("studysager_username"));
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(false);

  const applyAuth = useCallback((data) => {
    localStorage.setItem("studysager_token", data.access_token);
    localStorage.setItem("studysager_username", data.username);
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
    localStorage.removeItem("studysager_token");
    localStorage.removeItem("studysager_username");
    setToken(null);
    setUsername(null);
    setProfile(null);
  }, []);

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
