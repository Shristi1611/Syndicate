import { useEffect, useMemo, useRef, useState } from "react";

import "./Hero.css";

const VIDEO_SRC = "/earth_scrub.mp4";
const POSTER_SRC = "/earth_poster.jpg";
const FPS = 30;
const VIDEO_SHARE = 0.8; // the video plays across this share of the scroll, then holds on India
const EASE = 0.14;       // how quickly the picture catches up with the scroll bar

const clamp01 = (x) => Math.min(1, Math.max(0, x));
const smooth = (x) => {
  const t = clamp01(x);
  return t * t * (3 - 2 * t);
};

export default function Hero() {
  const trackRef = useRef(null);
  const videoRef = useRef(null);
  const wordRef = useRef(null);
  const cueRef = useRef(null);
  const [failed, setFailed] = useState(false);

  // People who ask for less motion get the still picture instead of a scrubbed video.
  const still = useMemo(
    () => failed || window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    [failed],
  );

  useEffect(() => {
    if (still) return;

    const track = trackRef.current;
    const video = videoRef.current;
    const word = wordRef.current;
    const cue = cueRef.current;

    let target = 0; // where the scroll bar says we are, from 0 to 1
    let shown = 0;  // where the picture is, easing towards the target
    let lastFrame = -1;
    let frame = 0;

    const measure = () => {
      const range = track.offsetHeight - window.innerHeight;
      target = range > 0 ? clamp01(-track.getBoundingClientRect().top / range) : 0;
    };

    const tick = () => {
      shown += (target - shown) * EASE;
      if (Math.abs(target - shown) < 0.0004) shown = target;

      // Move the video to the matching frame. Only seek when the frame actually changes.
      if (video.duration) {
        const frames = Math.round(video.duration * FPS);
        const index = Math.round(clamp01(shown / VIDEO_SHARE) * (frames - 1));
        if (index !== lastFrame) {
          video.currentTime = (index + 0.5) / FPS;
          lastFrame = index;
        }
      }

      // The wordmark melts away as the Earth arrives.
      const away = smooth(shown / 0.12);
      word.style.opacity = String(1 - away);
      word.style.transform = `translate(-50%, -50%) scale(${1 + 0.14 * away})`;
      word.style.filter = `blur(${(away * 10).toFixed(1)}px)`;
      cue.style.opacity = String(1 - smooth(shown / 0.04));

      frame = requestAnimationFrame(tick);
    };

    window.addEventListener("scroll", measure, { passive: true });
    window.addEventListener("resize", measure);
    measure();
    shown = target; // a reload halfway down the page starts in the right place
    frame = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", measure);
      window.removeEventListener("resize", measure);
    };
  }, [still]);

  return (
    <div className={still ? "journey journey-still" : "journey"} ref={trackRef}>
      <div className="pin">
        {still ? (
          <img className="earth" src={POSTER_SRC} alt="Earth, with India in the middle" />
        ) : (
          <video
            ref={videoRef}
            className="earth"
            src={VIDEO_SRC}
            muted
            playsInline
            preload="auto"
            aria-hidden="true"
            onError={() => setFailed(true)}
          />
        )}

        <h1 className="wordmark" ref={wordRef}>
          Synd<em>icate</em>
        </h1>

        <div className="cue" ref={cueRef}>
          <s />
          Scroll
        </div>
      </div>
    </div>
  );
}