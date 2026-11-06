import { useEffect, useRef } from "react";

import "./Cursor.css";

// A soft dot that follows the mouse and grows over anything clickable.
// It only appears on devices with a real mouse.
export default function Cursor() {
  const dotRef = useRef(null);

  useEffect(() => {
    if (!window.matchMedia("(hover: hover) and (pointer: fine)").matches) return;

    const dot = dotRef.current;
    const target = { x: 0, y: 0 };
    const pos = { x: 0, y: 0 };
    let seen = false;
    let frame = 0;

    const onMove = (e) => {
      target.x = e.clientX;
      target.y = e.clientY;
      if (!seen) {
        pos.x = target.x;
        pos.y = target.y;
        seen = true;
        dot.classList.add("is-visible");
      }
      dot.classList.toggle("wide", Boolean(e.target.closest(".card, a, button")));
    };
    const onLeave = () => dot.classList.remove("is-visible");
    const onEnter = () => seen && dot.classList.add("is-visible");

    const loop = () => {
      pos.x += (target.x - pos.x) * 0.2;
      pos.y += (target.y - pos.y) * 0.2;
      dot.style.transform = `translate3d(${pos.x}px, ${pos.y}px, 0)`;
      frame = requestAnimationFrame(loop);
    };

    document.addEventListener("pointermove", onMove);
    document.documentElement.addEventListener("mouseleave", onLeave);
    document.documentElement.addEventListener("mouseenter", onEnter);
    frame = requestAnimationFrame(loop);

    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("pointermove", onMove);
      document.documentElement.removeEventListener("mouseleave", onLeave);
      document.documentElement.removeEventListener("mouseenter", onEnter);
    };
  }, []);

  return <div className="dot" ref={dotRef} aria-hidden="true" />;
}