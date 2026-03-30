import { useState, useEffect } from "react";
import { useLocation } from "wouter";

// ─── Types ────────────────────────────────────────────────────────────────────

type Scenario = "emergency" | "before" | "question";

interface ScenarioOption {
  id: Scenario;
  icon: string;
  label: string;
  sublabel: string;
  description: string;
  examples: string[];
  route: string;
  accentColor: string;
  bgFrom: string;
  bgTo: string;
  borderColor: string;
  textColor: string;
  badgeColor: string;
  badgeText: string;
  badgeBg: string;
}

// ─── Scenario config ─────────────────────────────────────────────────────────

const SCENARIOS: ScenarioOption[] = [
  {
    id: "emergency",
    icon: "⚡",
    label: "Emergency",
    sublabel: "Active complication",
    description: "Something has gone wrong. Get the protocol now.",
    examples: [
      "Blanching after filler injection",
      "Suspected vascular occlusion",
      "Anaphylaxis signs in clinic",
      "Unexpected pain or vision change",
    ],
    route: "/emergency?guided=true",
    accentColor: "#C0392B",
    bgFrom: "#FEF2F2",
    bgTo: "#FFF5F5",
    borderColor: "#FECACA",
    textColor: "#991B1B",
    badgeColor: "#991B1B",
    badgeText: "CRITICAL",
    badgeBg: "#FEE2E2",
  },
  {
    id: "before",
    icon: "💉",
    label: "Before Procedure",
    sublabel: "Pre-treatment risk check",
    description: "Assess the patient before injection. Know the risks first.",
    examples: [
      "Tear trough — patient on anticoagulants",
      "Lip filler — prior vascular history",
      "Glabellar toxin — first-time patient",
      "High-risk zone assessment",
    ],
    route: "/safety-check",
    accentColor: "#0F6E56",
    bgFrom: "#F0FDF9",
    bgTo: "#F6FFFD",
    borderColor: "#6EE7C4",
    textColor: "#065F46",
    badgeColor: "#065F46",
    badgeText: "SAFETY CHECK",
    badgeBg: "#D1FAE5",
  },
  {
    id: "question",
    icon: "🧠",
    label: "Clinical Question",
    sublabel: "Evidence search",
    description: "Look up evidence, protocols, dosing, or technique guidance.",
    examples: [
      "Cannula vs needle — vascular safety",
      "Hyaluronidase dosing after occlusion",
      "Tyndall effect management",
      "Botulinum toxin dilution for forehead",
    ],
    route: "/ask",
    accentColor: "#1E40AF",
    bgFrom: "#EFF6FF",
    bgTo: "#F5F8FF",
    borderColor: "#BFDBFE",
    textColor: "#1E3A8A",
    badgeColor: "#1E3A8A",
    badgeText: "EVIDENCE",
    badgeBg: "#DBEAFE",
  },
];

// ─── Animated counter for stats ──────────────────────────────────────────────

function useCountUp(target: number, duration: number = 1200, delay: number = 0) {
  const [value, setValue] = useState(0);
  useEffect(() => {
    const timeout = setTimeout(() => {
      const start = Date.now();
      const tick = () => {
        const elapsed = Date.now() - start;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        setValue(Math.round(eased * target));
        if (progress < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }, delay);
    return () => clearTimeout(timeout);
  }, [target, duration, delay]);
  return value;
}

// ─── Stat pill ────────────────────────────────────────────────────────────────

function StatPill({ value, label, delay }: { value: string; label: string; delay: number }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setVisible(true), delay);
    return () => clearTimeout(t);
  }, [delay]);

  return (
    <div
      style={{
        opacity: visible ? 1 : 0,
        transform: visible ? "translateY(0)" : "translateY(6px)",
        transition: "opacity 0.5s ease, transform 0.5s ease",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: "2px",
      }}
    >
      <span style={{ fontSize: "18px", fontWeight: 700, color: "#0F6E56", fontFamily: "'DM Serif Display', Georgia, serif", letterSpacing: "-0.02em" }}>
        {value}
      </span>
      <span style={{ fontSize: "11px", color: "#6B7280", fontFamily: "'DM Sans', sans-serif", letterSpacing: "0.04em", textTransform: "uppercase" }}>
        {label}
      </span>
    </div>
  );
}

// ─── Scenario card ────────────────────────────────────────────────────────────

function ScenarioCard({
  scenario,
  isHovered,
  onHover,
  onLeave,
  onClick,
  animIndex,
}: {
  scenario: ScenarioOption;
  isHovered: boolean;
  onHover: () => void;
  onLeave: () => void;
  onClick: () => void;
  animIndex: number;
}) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setMounted(true), 200 + animIndex * 120);
    return () => clearTimeout(t);
  }, [animIndex]);

  return (
    <button
      onClick={onClick}
      onMouseEnter={onHover}
      onMouseLeave={onLeave}
      style={{
        all: "unset",
        cursor: "pointer",
        display: "flex",
        flexDirection: "column",
        background: isHovered
          ? `linear-gradient(145deg, ${scenario.bgFrom}, white)`
          : "white",
        border: `1.5px solid ${isHovered ? scenario.accentColor : scenario.borderColor}`,
        borderRadius: "16px",
        padding: "28px 24px 24px",
        transition: "all 0.22s cubic-bezier(0.4, 0, 0.2, 1)",
        boxShadow: isHovered
          ? `0 8px 32px ${scenario.accentColor}18, 0 2px 8px rgba(0,0,0,0.06)`
          : "0 1px 4px rgba(0,0,0,0.05)",
        transform: isHovered ? "translateY(-3px)" : "translateY(0)",
        opacity: mounted ? 1 : 0,
        position: "relative",
        overflow: "hidden",
        flex: 1,
        minWidth: 0,
      }}
    >
      {/* Subtle background accent */}
      <div
        style={{
          position: "absolute",
          top: 0,
          right: 0,
          width: "120px",
          height: "120px",
          background: `radial-gradient(circle at top right, ${scenario.accentColor}08, transparent 70%)`,
          pointerEvents: "none",
        }}
      />

      {/* Badge */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "20px" }}>
        <span
          style={{
            fontSize: "11px",
            fontWeight: 700,
            letterSpacing: "0.08em",
            color: scenario.badgeColor,
            background: scenario.badgeBg,
            padding: "3px 10px",
            borderRadius: "100px",
            fontFamily: "'DM Sans', sans-serif",
          }}
        >
          {scenario.badgeText}
        </span>
        <span style={{ fontSize: "28px", lineHeight: 1 }}>{scenario.icon}</span>
      </div>

      {/* Title */}
      <div style={{ marginBottom: "6px" }}>
        <div
          style={{
            fontSize: "22px",
            fontWeight: 700,
            color: "#111827",
            fontFamily: "'DM Serif Display', Georgia, serif",
            letterSpacing: "-0.02em",
            lineHeight: 1.2,
          }}
        >
          {scenario.label}
        </div>
        <div
          style={{
            fontSize: "13px",
            color: scenario.textColor,
            fontFamily: "'DM Sans', sans-serif",
            marginTop: "3px",
            fontWeight: 500,
          }}
        >
          {scenario.sublabel}
        </div>
      </div>

      {/* Description */}
      <p
        style={{
          fontSize: "14px",
          color: "#4B5563",
          fontFamily: "'DM Sans', sans-serif",
          lineHeight: 1.6,
          margin: "12px 0 20px",
        }}
      >
        {scenario.description}
      </p>

      {/* Examples */}
      <div style={{ display: "flex", flexDirection: "column", gap: "7px", marginBottom: "24px" }}>
        {scenario.examples.map((ex, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: "8px",
              fontSize: "12px",
              color: "#6B7280",
              fontFamily: "'DM Sans', sans-serif",
              lineHeight: 1.4,
            }}
          >
            <span style={{ color: scenario.accentColor, fontWeight: 700, flexShrink: 0, marginTop: "1px" }}>→</span>
            {ex}
          </div>
        ))}
      </div>

      {/* CTA */}
      <div style={{ marginTop: "auto" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "8px",
            background: isHovered ? scenario.accentColor : "transparent",
            border: `1.5px solid ${scenario.accentColor}`,
            borderRadius: "10px",
            padding: "11px 20px",
            transition: "all 0.18s ease",
          }}
        >
          <span
            style={{
              fontSize: "14px",
              fontWeight: 600,
              color: isHovered ? "white" : scenario.accentColor,
              fontFamily: "'DM Sans', sans-serif",
              transition: "color 0.18s ease",
            }}
          >
            {scenario.id === "emergency" ? "Open protocol" : scenario.id === "before" ? "Run safety check" : "Ask a question"}
          </span>
          <svg
            width="14"
            height="14"
            viewBox="0 0 14 14"
            fill="none"
            style={{
              color: isHovered ? "white" : scenario.accentColor,
              transition: "color 0.18s ease, transform 0.18s ease",
              transform: isHovered ? "translateX(2px)" : "translateX(0)",
            }}
          >
            <path d="M3 7h8M7 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
      </div>
    </button>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function ScenarioEntry() {
  const [, navigate] = useLocation();
  const [hovered, setHovered] = useState<Scenario | null>(null);
  const [headerVisible, setHeaderVisible] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setHeaderVisible(true), 80);
    return () => clearTimeout(t);
  }, []);

  const handleSelect = (scenario: ScenarioOption) => {
    navigate(scenario.route);
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#FAFAF9",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "40px 24px",
        fontFamily: "'DM Sans', sans-serif",
      }}
    >
      {/* Google Fonts import via style tag workaround */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@400;500;600;700&display=swap');
        * { box-sizing: border-box; }
        @media (max-width: 768px) {
          .scenario-grid { flex-direction: column !important; }
          .scenario-grid > * { min-width: unset !important; }
        }
      `}</style>

      <div style={{ width: "100%", maxWidth: "960px" }}>

        {/* Logo + header */}
        <div
          style={{
            textAlign: "center",
            marginBottom: "48px",
            opacity: headerVisible ? 1 : 0,
            transform: headerVisible ? "translateY(0)" : "translateY(-10px)",
            transition: "opacity 0.5s ease, transform 0.5s ease",
          }}
        >
          {/* Logo mark */}
          <div
            style={{
              width: "52px",
              height: "52px",
              borderRadius: "14px",
              background: "linear-gradient(135deg, #0F6E56, #1D9E75)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              margin: "0 auto 16px",
              boxShadow: "0 4px 16px rgba(15, 110, 86, 0.25)",
            }}
          >
            <svg width="26" height="26" viewBox="0 0 26 26" fill="none">
              <path d="M13 3L4 8.5V17.5L13 23L22 17.5V8.5L13 3Z" stroke="white" strokeWidth="1.8" strokeLinejoin="round" />
              <path d="M9 13.5L11.5 16L17 10.5" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>

          <div
            style={{
              fontSize: "13px",
              fontWeight: 600,
              letterSpacing: "0.12em",
              color: "#0F6E56",
              textTransform: "uppercase",
              marginBottom: "14px",
              fontFamily: "'DM Sans', sans-serif",
            }}
          >
            AesthetiCite
          </div>

          <h1
            style={{
              fontSize: "clamp(28px, 4vw, 42px)",
              fontWeight: 700,
              color: "#111827",
              fontFamily: "'DM Serif Display', Georgia, serif",
              letterSpacing: "-0.03em",
              lineHeight: 1.15,
              margin: "0 0 14px",
            }}
          >
            What are you dealing with right now?
          </h1>

          <p
            style={{
              fontSize: "16px",
              color: "#6B7280",
              maxWidth: "480px",
              margin: "0 auto",
              lineHeight: 1.6,
              fontFamily: "'DM Sans', sans-serif",
            }}
          >
            Choose your situation and get exactly what you need — protocol, risk check, or evidence — in under 2 seconds.
          </p>
        </div>

        {/* Scenario cards */}
        <div
          className="scenario-grid"
          style={{
            display: "flex",
            gap: "16px",
            marginBottom: "40px",
            alignItems: "stretch",
          }}
        >
          {SCENARIOS.map((s, i) => (
            <ScenarioCard
              key={s.id}
              scenario={s}
              isHovered={hovered === s.id}
              onHover={() => setHovered(s.id)}
              onLeave={() => setHovered(null)}
              onClick={() => handleSelect(s)}
              animIndex={i}
            />
          ))}
        </div>

        {/* Stats bar */}
        <div
          style={{
            display: "flex",
            justifyContent: "center",
            gap: "40px",
            padding: "20px 32px",
            background: "white",
            borderRadius: "12px",
            border: "1px solid #E5E7EB",
            flexWrap: "wrap",
          }}
        >
          <StatPill value="1.9M+" label="Publications" delay={600} />
          <div style={{ width: "1px", background: "#E5E7EB", alignSelf: "stretch" }} />
          <StatPill value="6" label="Complication protocols" delay={750} />
          <div style={{ width: "1px", background: "#E5E7EB", alignSelf: "stretch" }} />
          <StatPill value="22+" label="Languages" delay={900} />
          <div style={{ width: "1px", background: "#E5E7EB", alignSelf: "stretch" }} />
          <StatPill value="<1s" label="Protocol response" delay={1050} />
        </div>

        {/* Subtle footer note */}
        <p
          style={{
            textAlign: "center",
            fontSize: "12px",
            color: "#9CA3AF",
            marginTop: "24px",
            fontFamily: "'DM Sans', sans-serif",
            lineHeight: 1.6,
          }}
        >
          Clinical decision support · Not a substitute for clinical judgement · For registered clinicians only
        </p>
      </div>
    </div>
  );
}
