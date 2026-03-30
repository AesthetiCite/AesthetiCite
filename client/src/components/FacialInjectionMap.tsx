/**
 * FacialInjectionMap.tsx — Improvement 2
 * Tappable SVG facial map for injection region selection.
 * Replaces the free-text injected_region field in the visual differential flow.
 *
 * Usage:
 *   <FacialInjectionMap selected={region} onChange={setRegion} />
 */

import React, { useState } from "react";

export const FACIAL_REGIONS = [
  { id: "forehead",       label: "Forehead",           risk: "high"   },
  { id: "temple",         label: "Temple",             risk: "high"   },
  { id: "glabella",       label: "Glabella",           risk: "high"   },
  { id: "periorbital",    label: "Periorbital / Tear trough", risk: "high" },
  { id: "nose",           label: "Nose",               risk: "high"   },
  { id: "nasolabial",     label: "Nasolabial fold",    risk: "medium" },
  { id: "cheek",          label: "Cheek",              risk: "medium" },
  { id: "lips",           label: "Lips",               risk: "medium" },
  { id: "chin",           label: "Chin",               risk: "low"    },
  { id: "jawline",        label: "Jawline",            risk: "low"    },
  { id: "neck",           label: "Neck",               risk: "low"    },
] as const;

export type FacialRegionId = typeof FACIAL_REGIONS[number]["id"];

interface RegionZone {
  id: FacialRegionId;
  label: string;
  risk: "high" | "medium" | "low";
  // SVG ellipse parameters
  cx: number; cy: number; rx: number; ry: number;
  // label offset
  lx: number; ly: number;
}

const ZONES: RegionZone[] = [
  { id: "forehead",    label: "Forehead",    risk: "high",   cx: 200, cy: 72,  rx: 68, ry: 28, lx: 200, ly: 68  },
  { id: "temple",      label: "Temple",      risk: "high",   cx: 290, cy: 92,  rx: 28, ry: 22, lx: 290, ly: 88  },
  { id: "glabella",    label: "Glabella",    risk: "high",   cx: 200, cy: 112, rx: 24, ry: 16, lx: 200, ly: 108 },
  { id: "periorbital", label: "Tear trough", risk: "high",   cx: 248, cy: 130, rx: 26, ry: 14, lx: 248, ly: 126 },
  { id: "nose",        label: "Nose",        risk: "high",   cx: 200, cy: 160, rx: 20, ry: 26, lx: 200, ly: 156 },
  { id: "cheek",       label: "Cheek",       risk: "medium", cx: 258, cy: 168, rx: 32, ry: 26, lx: 258, ly: 164 },
  { id: "nasolabial",  label: "NLF",         risk: "medium", cx: 234, cy: 186, rx: 16, ry: 18, lx: 234, ly: 182 },
  { id: "lips",        label: "Lips",        risk: "medium", cx: 200, cy: 206, rx: 30, ry: 14, lx: 200, ly: 202 },
  { id: "chin",        label: "Chin",        risk: "low",    cx: 200, cy: 238, rx: 26, ry: 18, lx: 200, ly: 234 },
  { id: "jawline",     label: "Jawline",     risk: "low",    cx: 252, cy: 222, rx: 28, ry: 14, lx: 252, ly: 218 },
];

const RISK_COLORS = {
  high:   { idle: "#FEE2E2", hover: "#FECACA", selected: "#EF4444", stroke: "#F87171",  text: "#991B1B" },
  medium: { idle: "#FEF3C7", hover: "#FDE68A", selected: "#F59E0B", stroke: "#FCD34D",  text: "#92400E" },
  low:    { idle: "#D1FAE5", hover: "#A7F3D0", selected: "#10B981", stroke: "#6EE7B7",  text: "#065F46" },
};

interface Props {
  selected: FacialRegionId | null;
  onChange: (id: FacialRegionId) => void;
  disabled?: boolean;
}

export function FacialInjectionMap({ selected, onChange, disabled }: Props) {
  const [hovered, setHovered] = useState<FacialRegionId | null>(null);

  return (
    <div className="flex flex-col items-center gap-3">
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
        Tap the injection region
      </p>

      <div className="relative w-full max-w-xs">
        <svg
          viewBox="0 0 400 310"
          className="w-full"
          style={{ userSelect: "none" }}
        >
          {/* Face outline */}
          <ellipse
            cx="200" cy="170" rx="110" ry="145"
            fill="none" stroke="var(--color-border-secondary, #d1d5db)"
            strokeWidth="1.5"
          />
          {/* Ear stubs */}
          <ellipse cx="92" cy="170" rx="10" ry="22" fill="none"
            stroke="var(--color-border-secondary, #d1d5db)" strokeWidth="1" />
          <ellipse cx="308" cy="170" rx="10" ry="22" fill="none"
            stroke="var(--color-border-secondary, #d1d5db)" strokeWidth="1" />
          {/* Neck */}
          <path d="M 172 312 L 172 296 Q 200 302 228 296 L 228 312"
            fill="none" stroke="var(--color-border-secondary, #d1d5db)" strokeWidth="1" />

          {/* Regions */}
          {ZONES.map((z) => {
            const isSelected = selected === z.id;
            const isHovered  = hovered  === z.id;
            const col = RISK_COLORS[z.risk];
            const fill = isSelected ? col.selected
                       : isHovered  ? col.hover
                       :              col.idle;
            const stroke = isSelected ? col.selected : col.stroke;
            const textColor = isSelected ? "#ffffff" : col.text;
            // mirror left-side zones
            const zones: RegionZone[] = [z];
            if (["periorbital","cheek","nasolabial","jawline"].includes(z.id)) {
              zones.push({ ...z, cx: 400 - z.cx, lx: 400 - z.lx } as RegionZone);
            }
            return zones.map((zone, idx) => (
              <g
                key={`${zone.id}-${idx}`}
                style={{ cursor: disabled ? "default" : "pointer" }}
                onClick={() => !disabled && onChange(zone.id)}
                onMouseEnter={() => !disabled && setHovered(zone.id)}
                onMouseLeave={() => setHovered(null)}
              >
                <ellipse
                  cx={zone.cx} cy={zone.cy} rx={zone.rx} ry={zone.ry}
                  fill={fill}
                  stroke={stroke}
                  strokeWidth={isSelected ? 2 : 1}
                  style={{ transition: "fill 0.12s, stroke 0.12s" }}
                />
                <text
                  x={zone.lx} y={zone.ly + 4}
                  textAnchor="middle"
                  fontSize="9"
                  fontWeight={isSelected ? "600" : "400"}
                  fill={textColor}
                  style={{ pointerEvents: "none" }}
                >
                  {zone.label}
                </text>
              </g>
            ));
          })}
        </svg>
      </div>

      {/* Risk legend */}
      <div className="flex items-center gap-4 text-xs text-gray-500">
        {(["high","medium","low"] as const).map((r) => (
          <span key={r} className="flex items-center gap-1">
            <span
              className="w-2.5 h-2.5 rounded-full inline-block"
              style={{ background: RISK_COLORS[r].selected }}
            />
            {r === "high" ? "High risk zone" : r === "medium" ? "Medium" : "Lower risk"}
          </span>
        ))}
      </div>

      {/* Selected label */}
      {selected && (
        <div className="text-sm font-medium text-gray-800">
          Selected:{" "}
          <span className="text-teal-700">
            {FACIAL_REGIONS.find(r => r.id === selected)?.label}
          </span>
          <button
            className="ml-2 text-xs text-gray-400 hover:text-gray-600"
            onClick={() => onChange(null as any)}
          >
            clear
          </button>
        </div>
      )}
    </div>
  );
}
