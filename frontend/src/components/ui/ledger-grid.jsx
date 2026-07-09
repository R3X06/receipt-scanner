export function LedgerGrid({
  minorColor = "rgba(253, 229, 229, 0.05)",
  majorColor = "rgba(57, 21, 91, 0.12)",
  minorSize = 6.5,
  majorSize = 2,
  mask = "radial-gradient(120% 100% at 50% 0%, black 40%, transparent 100%)",
}) {
  return (
    <div
      className="pointer-events-none absolute inset-0 z-0"
      style={{
        backgroundImage: `
          linear-gradient(${minorColor} 1px, transparent 1px),
          linear-gradient(90deg, ${minorColor} 1px, transparent 1px),
          linear-gradient(${majorColor} 1px, transparent 1px),
          linear-gradient(90deg, ${majorColor} 1px, transparent 1px)
        `,
        backgroundSize: `${minorSize}px ${minorSize}px, ${minorSize}px ${minorSize}px, ${majorSize}px ${majorSize}px, ${majorSize}px ${majorSize}px`,
        maskImage: mask,
        WebkitMaskImage: mask,
      }}
    />
  );
}