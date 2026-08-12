// Shown when the backend reports the LLM's response was cut off by hitting its token limit
// mid-generation (finish_reason == "length") rather than finishing naturally - so the user
// knows explicitly why a question/answer might be missing, instead of it just looking broken.
export default function TruncationBanner() {
  return (
    <div className="border border-amber-300 bg-amber-50 rounded-lg px-4 py-3 mb-4 text-sm text-amber-800">
      ✂️ <strong>The AI's response hit its length limit</strong> before finishing — one or more
      questions/answers may be missing. This isn't an error with the app; try again, ask for
      fewer questions, or switch the Answer engine in the sidebar (some models are more concise
      than others).
    </div>
  );
}
