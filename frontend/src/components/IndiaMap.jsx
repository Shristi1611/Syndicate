import { useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { FRAME, geometryToPath, project } from "../geo.js";
import "./IndiaMap.css";

// Labels sit to the right of a pin, except on these, where the right side is crowded or off the map.
const LABEL_LEFT = new Set(["Rajasthan", "Punjab", "Goa", "Maharashtra", "Kerala"]);
const SHORT = { "Andaman and Nicobar Islands": "Andaman & Nicobar" };
const HIDE_DELAY_MS = 220; // lets the pointer travel from a state to its card without the card vanishing

export default function IndiaMap({ geo, states, onPickCity }) {
  const [open, setOpen] = useState(null); // { name, x, y } on the screen, or null
  const timer = useRef(0);
  const pinRefs = useRef({});

  const shapes = useMemo(
    () =>
      geo.features.map((f) => ({
        kind: f.properties.kind,
        name: f.properties.name,
        ours: f.properties.ours,
        d: geometryToPath(f.geometry),
      })),
    [geo],
  );
  const outline = shapes.find((s) => s.kind === "outline");
  const pieces = shapes.filter((s) => s.kind !== "outline");

  const pins = useMemo(() => states.map((s) => ({ ...s, ...project(s.lon, s.lat) })), [states]);

  function show(name) {
    clearTimeout(timer.current);
    const el = pinRefs.current[name];
    if (!el) return;
    const box = el.getBoundingClientRect();
    setOpen({ name, x: box.left + box.width / 2, y: box.top + box.height / 2 });
  }

  function hide() {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setOpen(null), HIDE_DELAY_MS);
  }

  const current = open && states.find((s) => s.name === open.name);

  return (
    <>
      <svg className="india-svg" viewBox={`0 0 ${FRAME} ${FRAME}`} aria-hidden="true">
        {pieces.map((s) => (
          <path
            key={s.name}
            d={s.d}
            fillRule="evenodd"
            className={s.ours ? (open?.name === s.ours ? "state ours hot" : "state ours") : "state"}
            data-hover={s.ours ? "" : undefined}
            onMouseEnter={s.ours ? () => show(s.ours) : undefined}
            onMouseLeave={s.ours ? hide : undefined}
          />
        ))}
        <path className="india-outline" d={outline.d} fillRule="evenodd" />
      </svg>

      <div className="pins">
        {pins.map((p) => (
          <button
            key={p.name}
            type="button"
            ref={(el) => (pinRefs.current[p.name] = el)}
            className={["map-pin", LABEL_LEFT.has(p.name) ? "left" : "", open?.name === p.name ? "active" : ""].join(" ")}
            style={{ left: `${(p.x / FRAME) * 100}%`, top: `${(p.y / FRAME) * 100}%` }}
            data-hover=""
            aria-label={`${p.name}: ${p.cities.map((c) => c.name).join(", ")}`}
            onMouseEnter={() => show(p.name)}
            onMouseLeave={hide}
            onFocus={() => show(p.name)}
            onBlur={hide}
          >
            <span className="pin-dot" />
            <span className="pin-label">{SHORT[p.name] || p.name}</span>
          </button>
        ))}
      </div>

      {current &&
        createPortal(
          <aside
            className="state-card"
            style={{
              left: open.x,
              top: Math.min(Math.max(open.y, 150), window.innerHeight - 150),
              transform:
                open.x > window.innerWidth * 0.58
                  ? "translate(calc(-100% - 26px), -50%)"
                  : "translate(26px, -50%)",
            }}
            onMouseEnter={() => clearTimeout(timer.current)}
            onMouseLeave={hide}
          >
            <h3>{current.name}</h3>
            <p className="state-card-sub">
              {current.cities.length === 1 ? "1 destination" : `${current.cities.length} destinations`}
            </p>
            <ul>
              {current.cities.map((city) => (
                <li key={city.name}>
                  <button
                    type="button"
                    data-hover=""
                    onClick={() => onPickCity?.({ ...city, state: current.name })}
                  >
                    <span className="city-name">{city.name}</span>
                    <span className="city-tag">{city.tagline}</span>
                  </button>
                </li>
              ))}
            </ul>
          </aside>,
          document.body,
        )}
    </>
  );
}