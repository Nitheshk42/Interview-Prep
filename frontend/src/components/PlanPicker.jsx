import { useState, useEffect } from "react";
import * as api from "../api/client";

// Static display metadata for each tier - prices are what's actually configured in Stripe
// (this is just the label shown to the user; the real charge amount lives on the Stripe price
// object itself, not here). Only shown if the backend's /payments/plans says that tier's price ID
// is actually configured - see PlanPicker's availableTiers prop.
const PLAN_META = {
  sprint: { name: "Career Sprint", price: "$29 one-time", blurb: "Unlimited use for 14 days - built for an interview coming up fast." },
  student: { name: "Student", price: "$15 one-time", blurb: "Same 14-day unlimited access as Career Sprint, discounted for students." },
  pro_monthly: { name: "Pro", price: "$12/month", blurb: "Unlimited use every month, for ongoing job searching - cancel any time." },
};

// A small modal listing whichever tiers are actually turned on (see /payments/plans), each
// starting its own Stripe Checkout session for that specific tier. Used from both the sidebar's
// "Upgrade" button and the inline UpgradeBanner shown when a free-tier cap is hit.
export default function PlanPicker({ onClose }) {
  const [busyTier, setBusyTier] = useState(null);
  const [plans, setPlans] = useState(null); // null = loading
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    api.getPaymentPlans()
      .then((res) => setPlans(res.available_tiers || []))
      .catch(() => setLoadError("Couldn't load plans right now."));
  }, []);

  async function handlePick(tier) {
    setBusyTier(tier);
    try {
      const { checkout_url } = await api.createCheckout(tier);
      window.location.href = checkout_url;
    } catch (err) {
      alert(err.status === 503
        ? "That plan isn't available yet - check back soon."
        : (err.message || "Something went wrong starting checkout."));
      setBusyTier(null);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/30 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-xl max-w-md w-full p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-medium text-gray-900">Choose a plan</h2>
          <button type="button" onClick={onClose} className="text-gray-400 hover:text-gray-600 text-sm">✕</button>
        </div>

        {plans === null && !loadError && <p className="text-sm text-gray-400">Loading plans...</p>}
        {loadError && <p className="text-sm text-red-600">{loadError}</p>}
        {plans && plans.length === 0 && (
          <p className="text-sm text-gray-400">No plans are available yet - check back soon.</p>
        )}

        <div className="space-y-2.5">
          {(plans || []).map((tier) => {
            const meta = PLAN_META[tier];
            if (!meta) return null;
            return (
              <button
                key={tier}
                type="button"
                onClick={() => handlePick(tier)}
                disabled={busyTier !== null}
                className="w-full text-left border border-gray-200 rounded-xl p-3 hover:border-accent hover:bg-accent/5 transition disabled:opacity-60"
              >
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-gray-900">{meta.name}</p>
                  <p className="text-sm font-medium text-accent">{meta.price}</p>
                </div>
                <p className="text-xs text-gray-500 mt-1">{meta.blurb}</p>
                {busyTier === tier && <p className="text-xs text-accent mt-1">Starting checkout...</p>}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
