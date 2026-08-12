import { useEffect, useRef, useState } from "react";

// Voice-to-text using the browser's built-in Web Speech API - no backend, no API key, works
// out of the box in Chrome/Edge (not in VS Code's embedded browser preview - that's a
// restricted webview without network access to Chrome's recognition service).
//
// continuous=true means it keeps listening until the user clicks the button again, rather
// than auto-cutting after a few seconds of silence. Clicking stop both finalizes the
// transcript AND submits the question - the mic's stop button doubles as "send."
//
// Props:
//   value        - the current input text (so the final transcript can be read back out and
//                  submitted the moment recording stops)
//   onResult     - called with each newly-recognized chunk of speech (parent appends it)
//   onAutoSubmit - called with the final full text when the user manually stops recording
//   disabled
export default function MicButton({ value, onResult, onAutoSubmit, disabled }) {
  const SpeechRecognition =
    typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);
  const [listening, setListening] = useState(false);
  const [supported] = useState(() => Boolean(SpeechRecognition));
  const [errorMsg, setErrorMsg] = useState("");
  const recognitionRef = useRef(null);
  const manualStopRef = useRef(false);

  // Recognition event handlers are attached once (see effect below) and must never close over
  // stale props - React re-renders create new `value`/`onResult`/`onAutoSubmit` each time, so
  // these refs are refreshed every render (a plain assignment in the render body, not inside
  // an effect) and the handlers read from the ref at call-time instead of capturing a snapshot.
  const valueRef = useRef(value);
  valueRef.current = value;
  const onResultRef = useRef(onResult);
  onResultRef.current = onResult;
  const onAutoSubmitRef = useRef(onAutoSubmit);
  onAutoSubmitRef.current = onAutoSubmit;

  const ERROR_MESSAGES = {
    "not-allowed": "Microphone permission was denied. Click the padlock/mic icon in the address bar and allow microphone access, then try again.",
    "service-not-allowed": "Microphone permission was denied. Check your browser's site settings for this page.",
    "no-speech": "Didn't catch that — no speech detected. Try again and speak right after clicking.",
    "audio-capture": "No microphone found. Check that one is connected and not in use by another app.",
    network: "Speech recognition needs an internet connection to reach the browser's recognition service.",
    aborted: "", // user-initiated stop, not a real error
  };

  useEffect(() => {
    if (!SpeechRecognition) return undefined;
    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = "en-US";

    recognition.onresult = (e) => {
      let transcript = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        transcript += e.results[i][0].transcript + " ";
      }
      transcript = transcript.trim();
      if (transcript) onResultRef.current(transcript);
    };
    recognition.onerror = (e) => {
      manualStopRef.current = false;
      setListening(false);
      setErrorMsg(ERROR_MESSAGES[e.error] ?? `Voice input error: ${e.error}`);
    };
    recognition.onstart = () => setErrorMsg("");
    recognition.onend = () => {
      setListening(false);
      if (manualStopRef.current) {
        manualStopRef.current = false;
        // Defer one tick so React has flushed the last onResult's state update into `value`
        // before we read it back out through valueRef and submit it.
        setTimeout(() => onAutoSubmitRef.current?.(valueRef.current), 0);
      }
    };

    recognitionRef.current = recognition;
    return () => recognition.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!supported) return null;

  function toggle() {
    if (listening) {
      manualStopRef.current = true;
      recognitionRef.current?.stop();
      setListening(false);
    } else {
      manualStopRef.current = false;
      setErrorMsg("");
      try {
        recognitionRef.current?.start();
        setListening(true);
      } catch {
        // start() throws if called while already listening (rare double-click race) - ignore
      }
    }
  }

  return (
    <div className="relative shrink-0">
      <button
        type="button"
        onClick={toggle}
        disabled={disabled}
        title={listening ? "Stop recording and send" : "Speak your question instead of typing"}
        aria-label={listening ? "Stop voice input and send" : "Start voice input"}
        className={`shrink-0 w-9 h-9 flex items-center justify-center rounded-lg border text-base transition disabled:opacity-50 ${
          listening
            ? "bg-red-500 border-red-500 text-white animate-pulse"
            : "border-gray-300 text-gray-500 hover:bg-gray-50"
        }`}
      >
        {listening ? "⏹" : "🎤"}
      </button>
      {errorMsg && (
        <div className="absolute bottom-full right-0 mb-2 w-56 text-[11px] bg-gray-900 text-white rounded-lg px-2 py-1.5 shadow-lg z-10">
          {errorMsg}
        </div>
      )}
    </div>
  );
}
