import { useEffect, useMemo, useRef, useState } from "react";

import { FRAME, fitView } from "../geo.js";
import IndiaMap from "./IndiaMap.jsx";
import "./Hero.css";

const VIDEO_SRC = "/earth_scrub.mp4";
const POSTER_SRC = "/earth_poster.jpg";
const GEO_SRC = "/data/india.json";
const FPS = 30;
const EASE = 0.14; // how quickly the picture catches up with the scroll bar

// The whole journey is one scroll, from 0 to 1. This is where each part happens.
const VIDEO_SHARE = 0.5; // 0.00 to 0.50: the Earth appears and turns to India
const ZOOM_AT = 0.5;     // 0.50 to 0.84: the camera pushes into India
const ZOOM_LEN = 0.34;
const FADE_AT = 0.58;    // the photo melts away...
const FADE_LEN = 0.16;
const REVEAL_AT = 0.6;   // ...while the drawn map comes in underneath it
const REVEAL_LEN = 0.18;
const PINS_AT = 0.8;     // then the state markers appear
const PINS_LEN = 0.07;
const READY_AT = 0.88;   // after this the map answers to the mouse

const clamp01 = (x) => Math.min(1, Math.max(0, x));
const smooth = (x) => {
  const t = clamp01(x);
  return t * t * (3 - 2 * t);
};
const easeInOut = (x) => {
  const t = clamp01(x);
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
};

export default function Hero({ states = [], onPickCity }) {
  const trackRef = useRef(null);
  const stageRef = useRef(null);
  const videoRef = useRef(null);
  const wordRef = useRef(null);
  const cueRef = useRef(null);
  const hintRef = useRef(null);
  const [geo, setGeo] = useState(null);
  const [failed, setFailed] = useState(false);

  // People who ask for less motion get the still picture instead of a scrubbed video.
  const still = useMemo(
    () => failed || window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    [failed],
  );

  useEffect(() => {
    let cancelled = false;
    fetch(GEO_SRC)
      .then((res) => {
        if (!res.ok) throw new Error("map file missing");
        return res.json();
      })
      .then((data) => {
        if (!cancelled) setGeo(data);
      })
      .catch(() => {}); // without the map file the Earth still plays, it just stops at India
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const track = trackRef.current;
    const stage = stageRef.current;
    const video = videoRef.current; // null when we show the still picture
    const word = wordRef.current;
    const cue = cueRef.current;
    const hint = hintRef.current;
    const media = stage.querySelector(".earth");
    const svg = stage.querySelector(".india-svg");
    const pins = stage.querySelector(".pins");

    const outline = geo?.features.find((f) => f.properties.kind === "outline");
    const view = outline ? fitView(outline.geometry) : null; // how far to zoom, and onto what

    let lastFrame = -1;

    // Draw the whole screen for one scroll position, p, from 0 to 1.
    const apply = (p) => {
      if (video && video.duration) {
        const frames = Math.round(video.duration * FPS);
        const index = Math.round(clamp01(p / VIDEO_SHARE) * (frames - 1));
        if (index !== lastFrame) {
          video.currentTime = (index + 0.5) / FPS;
          lastFrame = index;
        }
      }

      // The wordmark melts away as the Earth arrives.
      const away = smooth(p / 0.075);
      word.style.opacity = String(1 - away);
      word.style.transform = `translate(-50%, -50%) scale(${1 + 0.14 * away})`;
      word.style.filter = `blur(${(away * 10).toFixed(1)}px)`;
      cue.style.opacity = String(1 - smooth(p / 0.025));

      // Push into India. The zoom is exponential, so it feels even from start to finish.
      const e = easeInOut((p - ZOOM_AT) / ZOOM_LEN);
      const k = view ? Math.exp(Math.log(view.k) * e) : 1;
      const dx = view ? -(view.cx - FRAME / 2) * e : 0;
      const dy = view ? -(view.cy - FRAME / 2) * e : 0;
      stage.style.transform =
        `scale(${k.toFixed(4)}) translate(${((dx / FRAME) * 100).toFixed(3)}%, ${((dy / FRAME) * 100).toFixed(3)}%)`;
      stage.style.setProperty("--k", k.toFixed(4));

      // The photo gives way to the drawn map, and then the markers come in.
      media.style.opacity = view ? String(1 - smooth((p - FADE_AT) / FADE_LEN)) : "1";
      if (svg) svg.style.opacity = String(smooth((p - REVEAL_AT) / REVEAL_LEN));
      if (pins) pins.style.opacity = String(smooth((p - PINS_AT) / PINS_LEN));
      stage.classList.toggle("ready", Boolean(view) && p >= READY_AT);
      hint.style.opacity = view ? String(smooth((p - READY_AT) / 0.05)) : "0";
    };

    if (still) {
      apply(1); // no scrolling story: show the finished map
      return;
    }

    let target = 0; // where the scroll bar says we are, from 0 to 1
    let shown = 0;  // where the picture is, easing towards the target
    let frame = 0;

    const measure = () => {
      const range = track.offsetHeight - window.innerHeight;
      target = range > 0 ? clamp01(-track.getBoundingClientRect().top / range) : 0;
    };

    const tick = () => {
      shown += (target - shown) * EASE;
      if (Math.abs(target - shown) < 0.0004) shown = target;
      apply(shown);
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
  }, [still, geo, states]);

  return (
    <div className={still ? "journey journey-still" : "journey"} ref={trackRef}>
      <div className="screen">
        <div className="map-stage" ref={stageRef}>
          {still ? (
            <img className="earth" src={POSTER_SRC} alt="" />
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
          {geo && states.length > 0 && <IndiaMap geo={geo} states={states} onPickCity={onPickCity} />}
        </div>

        <h1 className="wordmark" ref={wordRef}>
          Synd<em>icate</em>
        </h1>

        <div className="cue" ref={cueRef}>
          <s />
          Scroll
        </div>

        <div className="hint" ref={hintRef}>
          Hover a state to see its cities
        </div>
      </div>
    </div>
  );
}