import { useEffect, useRef } from "react";

import { cardWidth, depthOf, fibonacciSphere, hueFor, perspective, sphereRadius } from "../sphereMath.js";
import "./Sphere.css";

const HEADLINE = ["A", "network", "of", "agents", "that", "negotiates", "your", "trip"];
const PITCH_LIMIT = 32; // how far up or down you can tilt, in degrees
const DRAG_DEGREES_PER_PIXEL = 0.13;
const CLICK_SLOP_MOUSE = 6;
const CLICK_SLOP_TOUCH = 14;

export default function Sphere({ destinations, onPick }) {
  const stageRef = useRef(null);
  const worldRef = useRef(null);
  const headlineRef = useRef(null);
  const cardRefs = useRef([]);

  useEffect(() => {
    const stage = stageRef.current;
    const world = worldRef.current;
    const headline = headlineRef.current;
    const cards = cardRefs.current;
    const points = fibonacciSphere(destinations.length);

    // Camera state. It lives in plain variables, so the frame loop never touches React.
    const state = {
      spin: 0,
      tilt: -4,
      camZ: 0,
      dragX: 0,
      dragY: 0,
      velX: 0,
      velY: 0,
      radius: 300,
      persp: 1150,
    };
    const last = cards.map(() => ({ opacity: -1, dim: -1 }));

    // ---- layout (runs on load and on resize) ----
    let lastW = 0;
    let lastH = 0;
    function layout(force) {
      const w = window.innerWidth;
      const h = window.innerHeight;
      if (!force && Math.abs(w - lastW) < 20 && Math.abs(h - lastH) < 20) return; // ignore small jitters
      lastW = w;
      lastH = h;

      state.radius = sphereRadius(w, h);
      state.persp = perspective(w);
      const cw = cardWidth(w, state.radius);

      stage.style.setProperty("--persp", `${state.persp}px`);
      stage.style.setProperty("--cw", `${cw}px`);
      stage.style.setProperty("--hw", w <= 380 ? "min(88vw, 320px)" : w <= 640 ? "min(84vw, 360px)" : "min(56vw, 640px)");

      cards.forEach((card, i) => {
        const p = points[i];
        card.style.transform =
          `translate3d(${p.x * state.radius}px, ${-p.y * state.radius}px, ${p.z * state.radius}px) ` +
          `rotateY(${p.lon}deg) rotateX(${p.lat}deg)`;
      });
    }
    layout(true);

    // ---- the frame loop ----
    let frame = 0;
    function tick() {
      // Momentum after letting go.
      if (!drag.active) {
        state.dragX += state.velX;
        state.dragY += state.velY;
        state.velX *= 0.94;
        state.velY *= 0.94;
        if (Math.abs(state.velX) < 0.002) state.velX = 0;
        if (Math.abs(state.velY) < 0.002) state.velY = 0;
        state.dragY = Math.max(-PITCH_LIMIT - state.tilt, Math.min(PITCH_LIMIT - state.tilt, state.dragY));
      }

      // Scroll only dollies the camera forward. It never flies through the sphere.
      const scrollRange = window.innerHeight * 0.16;
      const p = scrollRange > 0 ? Math.max(0, Math.min(1, window.scrollY / scrollRange)) : 0;
      const camTarget = p * Math.min(64, state.radius * 0.12);
      state.camZ += (camTarget - state.camZ) * 0.075;

      const sx = state.tilt + state.dragY;
      const sy = state.spin + state.dragX;

      world.style.transform = `translateZ(${state.camZ}px) rotateY(${sy}deg) rotateX(${sx}deg)`;

      // The headline cancels the world's rotation, so it stays square to the camera
      // and stays on the middle of the ring. Only this transform is ever written to it.
      headline.style.transform =
        `rotateX(${-sx}deg) rotateY(${-sy}deg) translateZ(${state.radius * 0.62}px)`;
      headline.style.opacity = String(Math.max(0, 1 - p * 0.55));

      // Back cards darken, near cards fade out as they pass the camera.
      const near = state.persp * 0.66;
      cards.forEach((card, i) => {
        const { depth } = depthOf(points[i], sy, sx);
        const base = 0.14 + 0.86 * Math.pow((depth + 1) / 2, 0.85);
        const shade = 1 - Math.min(1, p * 1.6);
        const dim = shade * (1 - base);
        const z = depth * state.radius + state.camZ;
        const opacity = z > near ? Math.max(0, 1 - (z - near) / 190) : 1;

        // Only write when the value changed, so idle frames cost almost nothing.
        const prev = last[i];
        if (Math.abs(prev.opacity - opacity) > 0.004) {
          card.style.opacity = opacity.toFixed(3);
          prev.opacity = opacity;
        }
        if (Math.abs(prev.dim - dim) > 0.004) {
          card.style.setProperty("--d", dim.toFixed(3));
          prev.dim = dim;
        }
      });

      frame = requestAnimationFrame(tick);
    }

    // ---- dragging ----
    const drag = { active: false, id: null, x: 0, y: 0, startX: 0, startY: 0, travelled: 0, card: null, touch: false, decided: false };

    function onDown(e) {
      drag.active = true;
      drag.id = e.pointerId;
      drag.x = drag.startX = e.clientX;
      drag.y = drag.startY = e.clientY;
      drag.travelled = 0;
      drag.touch = e.pointerType === "touch";
      drag.decided = !drag.touch; // mouse and pen rotate immediately
      drag.card = e.target.closest(".card");
      state.velX = state.velY = 0;
      if (!drag.touch) stage.setPointerCapture(e.pointerId);
    }

    function onMove(e) {
      if (!drag.active || e.pointerId !== drag.id) return;
      const dx = e.clientX - drag.x;
      const dy = e.clientY - drag.y;

      if (!drag.decided) {
        const total = Math.hypot(e.clientX - drag.startX, e.clientY - drag.startY);
        if (total < 10) return;
        // A mostly vertical swipe means the person is scrolling the page, so let it.
        if (Math.abs(e.clientY - drag.startY) > Math.abs(e.clientX - drag.startX) * 1.15) {
          drag.active = false;
          return;
        }
        drag.decided = true;
        stage.setPointerCapture(e.pointerId);
      }

      drag.x = e.clientX;
      drag.y = e.clientY;
      drag.travelled += Math.abs(dx) + Math.abs(dy);

      const yaw = dx * DRAG_DEGREES_PER_PIXEL;
      const pitch = dy * DRAG_DEGREES_PER_PIXEL;
      state.dragX += yaw;
      state.dragY = Math.max(-PITCH_LIMIT - state.tilt, Math.min(PITCH_LIMIT - state.tilt, state.dragY + pitch));
      state.velX = yaw;
      state.velY = pitch;
    }

    function onUp(e) {
      if (!drag.active || e.pointerId !== drag.id) return;
      drag.active = false;
      const slop = drag.touch ? CLICK_SLOP_TOUCH : CLICK_SLOP_MOUSE;
      // A short press is a click on whichever card was under the pointer at the start.
      if (drag.travelled <= slop && drag.card) {
        const index = Number(drag.card.dataset.idx);
        onPick?.(destinations[index], drag.card.getBoundingClientRect());
      }
      drag.card = null;
    }

    stage.addEventListener("pointerdown", onDown);
    stage.addEventListener("pointermove", onMove);
    stage.addEventListener("pointerup", onUp);
    stage.addEventListener("pointercancel", onUp);

    const onResize = () => layout(false);
    const onRotate = () => setTimeout(() => layout(true), 220);
    window.addEventListener("resize", onResize);
    window.addEventListener("orientationchange", onRotate);
    window.visualViewport?.addEventListener("resize", onResize);

    // The page is only 116vh tall, so the scrollable distance is the 16vh that drives the zoom.
    const clampScroll = () => {
      const max = window.innerHeight * 0.16;
      if (window.scrollY > max) window.scrollTo(0, max);
    };
    window.addEventListener("scroll", clampScroll, { passive: true });

    frame = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(frame);
      stage.removeEventListener("pointerdown", onDown);
      stage.removeEventListener("pointermove", onMove);
      stage.removeEventListener("pointerup", onUp);
      stage.removeEventListener("pointercancel", onUp);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("orientationchange", onRotate);
      window.visualViewport?.removeEventListener("resize", onResize);
      window.removeEventListener("scroll", clampScroll);
    };
  }, [destinations, onPick]);

  return (
    <>
      <div className="scrolltrack" aria-hidden="true" />
      <div className="stage" ref={stageRef}>
        <div className="world" ref={worldRef}>
          <div className="orb">
            {destinations.map((d, i) => (
              <div
                key={d.name}
                className="card"
                data-idx={i}
                ref={(el) => (cardRefs.current[i] = el)}
                style={{ "--hue": hueFor(d.region) }}
                role="button"
                aria-label={`${d.name}, ${d.region}. ${d.tagline}`}
              >
                <figure>
                  <span className="card-region">{d.region}</span>
                  <span className="card-name">{d.name}</span>
                  <span className="card-tag">{d.tagline}</span>
                </figure>
              </div>
            ))}
          </div>

          <h1 className="headline" ref={headlineRef}>
            <span className="inner">
              {HEADLINE.map((word, i) => (
                <span key={i} className="word" style={{ "--i": i }}>
                  {word}{" "}
                </span>
              ))}
            </span>
          </h1>
        </div>
      </div>
      <div className="vignette" aria-hidden="true" />
    </>
  );
}