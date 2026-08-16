import { createContext, useContext, useState } from "react";

// Mirrors src/llm_provider.py's PROVIDERS dict - keep the keys in sync with the backend.
export const PROVIDERS = {
  groq: "Groq (GPT-OSS 120B) — daily free limit",
  gemini: "Gemini (free tier) — separate daily limit",
};
const DEFAULT_PROVIDER = "groq";

const ProviderContext = createContext(null);

export function ProviderProvider({ children }) {
  const [provider, setProviderState] = useState(() => {
    const stored = localStorage.getItem("studysager_provider");
    // If a previously-selected provider (e.g. "gemini") is no longer in the picker, fall back
    // to the default rather than silently sending requests for an option nobody can see/change.
    return stored && PROVIDERS[stored] ? stored : DEFAULT_PROVIDER;
  });

  function setProvider(p) {
    localStorage.setItem("studysager_provider", p);
    setProviderState(p);
  }

  return (
    <ProviderContext.Provider value={{ provider, setProvider }}>
      {children}
    </ProviderContext.Provider>
  );
}

export function useProvider() {
  const ctx = useContext(ProviderContext);
  if (!ctx) throw new Error("useProvider must be used within ProviderProvider");
  return ctx;
}
