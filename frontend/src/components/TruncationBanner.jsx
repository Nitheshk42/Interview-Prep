// Shown when the backend reports the LLM's response was cut off by hitting its token limit
// mid-generation (finish_reason == "length") rather than finishing naturally - so the user
// knows explicitly why an answer might be missing/incomplete, instead of it just looking broken
// or badly written.
//
// variant="single": one answer got cut off mid-sentence (Chat Assistant, Hybrid Chat, EXP Level
// Answers - each of these is one self-contained answer, not a batch).
// variant="batch" (default): a multi-item generation (JD questions, vendor Q&A, etc.) may be
// missing one or more items because the whole batch hit the limit before finishing.
// compact: smaller padding/text, for placement inside a tight two-column layout.
export default function TruncationBanner({ variant = "batch", compact = false }) {
  const padding = compact ? "px-3 py-2 mb-2" : "px-4 py-3 mb-4";
  const textSize = compact ? "text-xs" : "text-sm";
  return (
    <div className={`border border-amber-300 bg-amber-50 rounded-lg ${padding} ${textSize} text-amber-800`}>
      {variant === "single" ? (
        <>
          ✂️ <strong>This answer hit its length limit</strong> and was cut off mid-sentence. This
          isn't an error with the app; try again, ask a more specific question, or switch the
          Answer engine in the sidebar (some models are more concise than others).
        </>
      ) : (
        <>
          ✂️ <strong>The AI's response hit its length limit</strong> before finishing — one or more
          questions/answers may be missing. This isn't an error with the app; try again, ask for
          fewer questions, or switch the Answer engine in the sidebar (some models are more concise
          than others).
        </>
      )}
    </div>
  );
}
