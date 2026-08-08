import { forwardRef, useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";

/**
 * Decorative 3D claymorphism geometric shapes, scattered absolutely
 * across a section and gently animated (float + spin).
 *
 * Each shape config: { type, size, x, y, color, spin?, float?,
 * duration?, delay? }
 * - type: circle | ring | square | squircle | blob | egg | pill
 * - x/y: percentage position within the container (0-100)
 * - color: Tailwind text color class (e.g. "text-primary/25") — used as
 *   currentColor so fills/borders adapt to the theme
 * - spin: continuous rotation in degrees (e.g. 360; negative = reverse)
 * - float: vertical bob distance in px (yoyo)
 */
export default function ClayShapes({ shapes, className = "" }) {
  const containerRef = useRef(null);
  const itemsRef = useRef([]);

  useGSAP(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    itemsRef.current.forEach((el, i) => {
      if (!el) return;
      const s = shapes[i];
      if (!s) return;
      const dur = s.duration || 6;
      const dly = s.delay || 0;

      // One seamless infinite timeline per shape: relative rotation keeps
      // accumulating (+=) and the bob toggles y, so neither ever "resets".
      const tl = gsap.timeline({ repeat: -1, delay: dly });
      if (s.spin) {
        const dir = s.spin < 0 ? "-=" : "+=";
        tl.to(
          el,
          { rotation: `${dir}${Math.abs(s.spin)}`, duration: dur, ease: "none" },
          0
        );
      }
      if (s.float) {
        tl.to(el, { y: s.float, duration: dur / 2, ease: "sine.inOut" }, 0)
          .to(el, { y: 0, duration: dur / 2, ease: "sine.inOut" });
      }
    });
  }, { scope: containerRef, dependencies: [shapes] });

  return (
    <div
      ref={containerRef}
      aria-hidden="true"
      className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`}
    >
      {shapes.map((s, i) => (
        <Shape
          key={i}
          ref={(n) => {
            itemsRef.current[i] = n;
          }}
          {...s}
        />
      ))}
    </div>
  );
}

const Shape = forwardRef(function Shape(
  { type, color = "text-primary/25", size, x, y },
  ref
) {
  const style = {
    left: `${x}%`,
    top: `${y}%`,
    width: type === "pill" ? size * 2 : size,
    height: size,
  };
  const cls = `clay-shape absolute ${color}`;

  let inner;
  switch (type) {
    case "ring":
      inner = (
        <div
          className="clay-ring h-full w-full rounded-full"
          style={{
            background: "transparent",
            border: `${Math.max(3, Math.round(size / 9))}px solid currentColor`,
          }}
        />
      );
      break;
    case "square":
      inner = <div className="clay h-full w-full rounded-2xl" style={{ background: "currentColor" }} />;
      break;
    case "squircle":
      inner = <div className="clay h-full w-full" style={{ background: "currentColor", borderRadius: "38%" }} />;
      break;
    case "blob":
      inner = (
        <div
          className="clay h-full w-full"
          style={{ background: "currentColor", borderRadius: "42% 58% 55% 45% / 45% 40% 60% 55%" }}
        />
      );
      break;
    case "egg":
      inner = (
        <div
          className="clay h-full w-full"
          style={{ background: "currentColor", borderRadius: "55% 45% 50% 50% / 48% 52% 45% 55%" }}
        />
      );
      break;
    case "pill":
      inner = <div className="clay h-full w-full rounded-full" style={{ background: "currentColor" }} />;
      break;
    case "circle":
    default:
      inner = <div className="clay h-full w-full rounded-full" style={{ background: "currentColor" }} />;
  }

  return (
    <div ref={ref} className={cls} style={style}>
      {inner}
    </div>
  );
});
