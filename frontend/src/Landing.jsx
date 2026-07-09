import KallaLogo from "./components/ui/KallaLogo";

export default function Landing({ onGetStarted }) {
  return (
    <div style={{
      minHeight: "100vh",
      background: "#07031a",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      padding: "40px 24px",
      fontFamily: "'Inter', system-ui, sans-serif",
      overflowX: "hidden",
    }}>

      {/* Logo — width caps at 460px on larger screens, shrinks to fit narrow
          phones via CSS instead of the fixed pixel width that was
          overflowing anything under ~500px wide */}
      <style>{`
        .kalla-landing-logo { width: min(72vw, 460px); }
        .kalla-landing-logo svg { width: 100%; height: auto; display: block; }
      `}</style>
      <div
        className="kalla-landing-logo"
        style={{ filter: "drop-shadow(0 0 12px #A855F7aa) drop-shadow(0 0 32px #A855F760)" }}
      >
        <KallaLogo width={460} />
      </div>

      {/* Tagline */}
      <p style={{
        marginTop: 18,
        fontSize: "clamp(10px, 2.5vw, 13px)",
        color: "hsla(270, 100%, 95%, 0.5)",
        letterSpacing: "0.08em",
        textTransform: "capitalize",
        textAlign: "center",
      }}>
        Your finances, engineered.
      </p>

      {/* Description */}
      <p style={{
        marginTop: 24,
        maxWidth: 480,
        textAlign: "center",
        color: "hsla(270, 100%, 95%, 0.3)",
        fontSize: "clamp(13px, 1.5vw, 15px)",
        lineHeight: 1.8,
      }}>
        KALLA is a personal finance tracker built on a double-entry ledger —
        every dollar is accounted for, every balance is derived from an
        immutable record. Not a spreadsheet. A financial model.
      </p>

      {/* Get Started — padding/minHeight sized to clear the ~44px minimum
          recommended touch target (was ~28-30px tall before) */}
      <button
        onClick={onGetStarted}
        style={{
          marginTop: 48,
          padding: "13px 32px",
          minHeight: 44,
          background: "#a955f7b1",
          color: "#ffffffe1",
          border: "none",
          borderRadius: 10,
          fontSize: 14,
          fontWeight: 600,
          letterSpacing: "0.05em",
          cursor: "pointer",
          boxShadow: "0 0 24px #A855F766",
          transition: "box-shadow 0.2s, transform 0.15s",
        }}
        onMouseEnter={e => {
          e.target.style.boxShadow = "0 0 40px #A855F7aa";
          e.target.style.transform = "translateY(-1px)";
        }}
        onMouseLeave={e => {
          e.target.style.boxShadow = "0 0 24px #A855F766";
          e.target.style.transform = "translateY(0)";
        }}
      >
        Get Started
      </button>
    </div>
  );
}