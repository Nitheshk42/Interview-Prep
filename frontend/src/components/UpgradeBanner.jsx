import { useState } from "react";
import * as api from "../api/client";

// Shown instead of a generic red error line when a request fails with 402 (free-tier daily cap
// hit - see backend/app/deps.py's enforce_usage_cap). Kept as its own component so every page
// that calls a capped endpoint (Chat/Hybrid/Level Answers, Resume Sync) can render the same
// upgrade prompt without duplicating the checkout-redirect logic.
export default function UpgradeBanner({ message }) {
  const [busy, setBusy] = useState(false);

  async function handleUpgrade() {
    setBusy(true);
    try {
      const { checkout_url } = await api.createCheckout();
      window.location.href = checkout_url;
    } catch (err) {
      alert(err.status === 503
        ? "Upgrades aren't available yet - check back soon."
        : (err.message || "Something went wrong starting checkout."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center justify-between gap-3 text-sm bg-accent/5 border border-accent/20 rounded-lg px-3 py-2 mt-2">
      <p className="text-gray-700">{message || "You've hit today's free limit."}</p>
      <button
        type="button"
        onClick={handleUpgrade}
        disabled={busy}
        className="shrink-0 bg-accent text-white rounded-lg px-3 py-1.5 text-xs font-medium hover:brightness-110 transition disabled:opacity-60"
      >
        {busy ? "Starting..." : "🚀 Upgrade"}
      </button>
    </div>
  );
}
