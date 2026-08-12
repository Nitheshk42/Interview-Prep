import { useState } from "react";
import { useAuth } from "../context/AuthContext";

// Mirrors src/auth_ui.py "Option A: minimal centered card" - centered column, icon + title +
// tagline above a bordered card with pill tabs for Login / Sign up.
export default function AuthPage() {
  const [tab, setTab] = useState("login");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const { doLogin, doSignup, loading } = useAuth();

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    try {
      if (tab === "login") {
        await doLogin(username, password);
      } else {
        await doSignup(username, email, password);
      }
    } catch (err) {
      setError(err.message || "Something went wrong.");
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-6">
          <div className="text-4xl mb-2">📚</div>
          <h1 className="text-2xl font-medium text-gray-900">StudySage</h1>
          <p className="text-sm text-gray-500 mt-1">Interview prep, grounded in your resume</p>
        </div>

        <div className="bg-white border border-gray-200 rounded-2xl shadow-sm p-6">
          <div className="flex bg-gray-100 rounded-full p-1 mb-6">
            {["login", "signup"].map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => { setTab(t); setError(""); }}
                className={`flex-1 py-1.5 text-sm font-medium rounded-full transition ${
                  tab === t ? "bg-white shadow text-accent" : "text-gray-500"
                }`}
              >
                {t === "login" ? "Login" : "Sign up"}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="space-y-3">
            <input
              type="text"
              placeholder="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
              required
            />
            {tab === "signup" && (
              <input
                type="email"
                placeholder="Email (optional)"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
              />
            )}
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
              required
            />

            {error && <p className="text-sm text-red-600">{error}</p>}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-accent text-white rounded-lg py-2 text-sm font-medium hover:brightness-110 transition disabled:opacity-60"
            >
              {loading ? "Please wait..." : tab === "login" ? "Log in" : "Create account"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
