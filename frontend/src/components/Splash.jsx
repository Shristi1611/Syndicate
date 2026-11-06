import { useEffect, useState } from "react";

import { get } from "../api.js";
import "./Splash.css";

// Everything the first screen needs. The bar fills as each one arrives.
const TASKS = [
  ["health", "/health"],
  ["destinations", "/destinations"],
  ["hotels", "/hotels"],
  ["personas", "/personas"],
];
const TOTAL = TASKS.length + 1; // plus the fonts
const MIN_HOLD_MS = 1150; // never flash past
const FADE_MS = 650;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export default function Splash({ onDone }) {
  const [loaded, setLoaded] = useState(0);
  const [leaving, setLeaving] = useState(false);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const born = performance.now();
    const data = {};

    setLoaded(0);
    setError("");
    setLeaving(false);

    const tick = () => {
      if (!cancelled) setLoaded((n) => n + 1);
    };

    const jobs = TASKS.map(([key, path]) =>
      get(path).then((value) => {
        data[key] = value;
        tick();
      }),
    );
    jobs.push(document.fonts.ready.then(tick));

    Promise.all(jobs)
      .then(async () => {
        await sleep(Math.max(0, MIN_HOLD_MS - (performance.now() - born)));
        if (cancelled) return;
        setLeaving(true);
        await sleep(FADE_MS);
        if (!cancelled) onDone(data);
      })
      .catch(() => {
        if (!cancelled) {
          setError("Could not reach the Syndicate server. Start the backend and try again.");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [attempt, onDone]);

  return (
    <div className={leaving ? "splash out" : "splash"} role="status" aria-live="polite">
      <div className="splash-mark">
        Synd<em>icate</em>
      </div>

      <div className="splash-bar" aria-hidden="true">
        <s style={{ transform: `scaleX(${loaded / TOTAL})` }} />
      </div>

      {error ? (
        <div className="splash-error">
          <p>{error}</p>
          <button type="button" onClick={() => setAttempt((n) => n + 1)}>
            Try again
          </button>
        </div>
      ) : (
        <div className="splash-tag">Negotiated Travel 2026</div>
      )}
    </div>
  );
}