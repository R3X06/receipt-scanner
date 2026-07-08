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
    }}>

      {/* Logo */}
      <div style={{ filter: "drop-shadow(0 0 12px #A855F7aa) drop-shadow(0 0 32px #A855F760)" }}>
        <KallaLogo width={460} />
      </div>

      {/* Tagline */}
      <p style={{
        marginTop: 18,
        font: "caption",
        fontSize: "clamp(12px, 1vw, 10px)",
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

      {/* Get Started */}
      <button
        onClick={onGetStarted}
        style={{
          marginTop: 48,
          padding: "7px 24px",
          background: "#a955f7b1",
          color: "#ffffffe1",
          border: "none",
          borderRadius: 10,
          fontSize: 12,
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