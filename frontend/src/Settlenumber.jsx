import { useEffect, useRef, useState } from "react";

function easeOutExpo(t) {
  return t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
}

/**
 * Counts up from 0 to `value` whenever a defined value arrives.
 * - No `active` prop: animates once per mount, as soon as `value` is
 *   non-null (fits WalletCard, which fully remounts each time its dialog
 *   opens, so mount == open).
 * - `active` prop passed: only animates while `active` is true, and
 *   re-animates every time `active` flips to true (fits ProfileCard,
 *   whose popover stays mounted and is only CSS-hidden, not unmounted).
 */
export default function SettleNumber({ value, active, duration = 900, format, className }) {
  const [display, setDisplay] = useState(0);
  const rafRef = useRef(null);

  useEffect(() => {
    if (value == null) return;
    if (active === false) return; // explicitly hidden — don't animate off-screen

    const from = 0;
    const to = value;
    const start = performance.now();

    function tick(now) {
      const p = Math.min((now - start) / duration, 1);
      setDisplay(from + (to - from) * easeOutExpo(p));
      if (p < 1) rafRef.current = requestAnimationFrame(tick);
    }
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, active, duration]);

  const fmt = format || ((v) => v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
  return <span className={className}>{fmt(display)}</span>;
}