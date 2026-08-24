import { useState } from "react";
import PlanPicker from "./PlanPicker";

// Shown instead of a generic red error line when a request fails with 402 (free-tier daily cap
// hit - see backend/app/deps.py's enforce_usage_cap). Kept as its own component so every page
// that calls a capped endpoint (Chat/Hybrid/Level Answers, Resume Sync) can render the same
// upgrade prompt without duplicating the plan-picker logic. Opens the same multi-tier PlanPicker
// as the sidebar's upgrade button, rather than jumping straight to a single hardcoded plan.
export default function UpgradeBanner({ message }) {
  const [pickerOpen, setPickerOpen] = useState(false);

  return (
    <div className="flex items-center justify-between gap-3 text-sm bg-accent/5 border border-accent/20 rounded-lg px-3 py-2 mt-2">
      <p className="text-gray-700">{message || "You've hit today's free limit."}</p>
      <button
        type="button"
        onClick={() => setPickerOpen(true)}
        className="shrink-0 bg-accent text-white rounded-lg px-3 py-1.5 text-xs font-medium hover:brightness-110 transition"
      >
        🚀 Upgrade
      </button>
      {pickerOpen && <PlanPicker onClose={() => setPickerOpen(false)} />}
    </div>
  );
}
