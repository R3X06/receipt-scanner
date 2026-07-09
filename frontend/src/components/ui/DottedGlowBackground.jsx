import { useEffect, useRef } from "react";

export default function DottedGlowBackground({ className = "" }) {
  const glowRef = useRef(null);

  useEffect(() => {
    function onMove(e) {
      if (!glowRef.current) return;
      const rect = glowRef.current.parentElement.getBoundingClientRect();
      glowRef.current.style.setProperty("--gx", `${e.clientX - rect.left}px`);
      glowRef.current.style.setProperty("--gy", `${e.clientY - rect.top}px`);
    }
    window.addEventListener("mousemove", onMove);
    return () => window.removeEventListener("mousemove", onMove);
  }, []);

  return (
    <div className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`} style={{ zIndex: 0 }}>
      <div
        className="absolute inset-0"
        style={{
          backgroundImage: "radial-gradient(rgba(255,255,255,0.14) 1px, transparent 1px)",
          backgroundSize: "18px 18px",
        }}
      />
      <div
        ref={glowRef}
        className="absolute inset-0 transition-opacity duration-300"
        style={{
          backgroundImage: "radial-gradient(rgba(168,85,247,0.6) 1px, transparent 1px)",
          backgroundSize: "18px 18px",
          WebkitMaskImage: "radial-gradient(220px 220px at var(--gx,50%) var(--gy,50%), black, transparent 70%)",
          maskImage: "radial-gradient(220px 220px at var(--gx,50%) var(--gy,50%), black, transparent 70%)",
        }}
      />
    </div>
  );
}