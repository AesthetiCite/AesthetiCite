/**
 * ReferenceImageComparison.tsx — Improvement 4
 *
 * Shows a side-by-side panel: the clinician's uploaded photo on the left,
 * and a reference image for the top diagnosis on the right.
 * Reference images are curated clinical illustrations — one per complication protocol.
 *
 * Reference images live in /public/reference-images/{protocol_key}.jpg
 * A placeholder SVG is shown if the image hasn't been added yet.
 *
 * Usage:
 *   <ReferenceImageComparison
 *     uploadedImageUrl={previewUrl}
 *     protocolKey="vascular_occlusion_ha_filler"
 *     diagnosis="Vascular occlusion after HA filler"
 *   />
 */

import React, { useState } from "react";
import { ImageOff, ZoomIn } from "lucide-react";

// ─────────────────────────────────────────────────────────────────
// Reference image registry
// Add a .jpg for each key to /public/reference-images/
// ─────────────────────────────────────────────────────────────────

interface ReferenceEntry {
  label: string;
  filename: string;
  caption: string;
  keyFindings: string[];
  urgency: string;
}

const REFERENCE_LIBRARY: Record<string, ReferenceEntry> = {
  vascular_occlusion_ha_filler: {
    label: "Vascular occlusion",
    filename: "vascular_occlusion_ha_filler.jpg",
    caption: "Blanching, livedo reticularis, and dusky discolouration after HA filler injection. Note the demarcated white patch and surrounding mottling.",
    keyFindings: [
      "Sharply demarcated blanching",
      "Livedo reticularis pattern",
      "Dusky / violaceous border",
      "Delayed capillary refill",
    ],
    urgency: "immediate",
  },
  tyndall_effect_ha_filler: {
    label: "Tyndall effect",
    filename: "tyndall_effect_ha_filler.jpg",
    caption: "Characteristic blue-grey discolouration over the tear trough or periorbital region caused by superficial HA filler placement.",
    keyFindings: [
      "Blue-grey discolouration",
      "Periorbital / tear trough location",
      "No blanching",
      "Develops weeks–months post-treatment",
    ],
    urgency: "routine",
  },
  anaphylaxis_in_clinic: {
    label: "Anaphylaxis",
    filename: "anaphylaxis_in_clinic.jpg",
    caption: "Generalised urticaria, erythema, and angioedema presentation following injectable product administration.",
    keyFindings: [
      "Widespread urticaria / hives",
      "Facial / tongue swelling",
      "Erythema",
      "Possible wheeze / hypotension",
    ],
    urgency: "immediate",
  },
  botulinum_toxin_ptosis: {
    label: "Toxin ptosis",
    filename: "botulinum_toxin_ptosis.jpg",
    caption: "Unilateral upper eyelid ptosis following botulinum toxin injection, caused by toxin diffusion to the levator palpebrae superioris.",
    keyFindings: [
      "Unilateral eyelid droop",
      "Onset 1–2 weeks post-toxin",
      "Brow ptosis vs eyelid ptosis",
      "No systemic symptoms",
    ],
    urgency: "same_day",
  },
  infection_or_biofilm_after_filler: {
    label: "Infection / biofilm",
    filename: "infection_or_biofilm_after_filler.jpg",
    caption: "Tender, erythematous swelling with warmth, presenting weeks to months after filler injection, consistent with biofilm or delayed infection.",
    keyFindings: [
      "Erythema and warmth",
      "Tender swelling",
      "Delayed onset (weeks–months)",
      "Possible fluctuance",
    ],
    urgency: "urgent",
  },
  filler_nodules_inflammatory_or_noninflammatory: {
    label: "Filler nodule",
    filename: "filler_nodules.jpg",
    caption: "Palpable nodule at injection site. Non-inflammatory nodules are firm and non-tender; inflammatory variants are red, warm, and painful.",
    keyFindings: [
      "Palpable lump",
      "Inflammation status varies",
      "Location matches injection site",
      "Timeline: weeks to months",
    ],
    urgency: "same_day",
  },
};

const URGENCY_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  immediate: { bg: "bg-red-100",    text: "text-red-700",    label: "IMMEDIATE" },
  urgent:    { bg: "bg-orange-100", text: "text-orange-700", label: "URGENT"    },
  same_day:  { bg: "bg-amber-100",  text: "text-amber-700",  label: "SAME DAY"  },
  routine:   { bg: "bg-green-100",  text: "text-green-700",  label: "ROUTINE"   },
};

// ─────────────────────────────────────────────────────────────────
// Placeholder SVG (renders when reference image not yet uploaded)
// ─────────────────────────────────────────────────────────────────

function PlaceholderImage({ label }: { label: string }) {
  return (
    <div className="w-full h-full min-h-[160px] flex flex-col items-center justify-center bg-gray-100 rounded-lg border-2 border-dashed border-gray-300 gap-2 p-4">
      <ImageOff className="w-8 h-8 text-gray-400" />
      <p className="text-xs text-gray-500 text-center font-medium">{label}</p>
      <p className="text-xs text-gray-400 text-center">
        Add reference image to
        <br />
        <code className="font-mono">/public/reference-images/</code>
      </p>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Zoomed overlay
// ─────────────────────────────────────────────────────────────────

function ZoomOverlay({ src, onClose }: { src: string; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-6"
      onClick={onClose}
    >
      <img
        src={src}
        alt="Zoomed reference"
        className="max-w-full max-h-full rounded-xl shadow-2xl object-contain"
        onClick={e => e.stopPropagation()}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────

interface Props {
  uploadedImageUrl: string | null;
  protocolKey: string | null;
  diagnosis: string;
  className?: string;
}

export function ReferenceImageComparison({
  uploadedImageUrl,
  protocolKey,
  diagnosis,
  className = "",
}: Props) {
  const [zoomSrc, setZoomSrc] = useState<string | null>(null);
  const [refError, setRefError] = useState(false);

  const entry = protocolKey ? REFERENCE_LIBRARY[protocolKey] : null;
  const refSrc = entry ? `/reference-images/${entry.filename}` : null;
  const urgencyBadge = entry ? URGENCY_BADGE[entry.urgency] : null;

  return (
    <div className={`rounded-xl border border-gray-200 bg-white overflow-hidden ${className}`}>
      {/* Header */}
      <div className="px-4 py-2.5 border-b border-gray-100 bg-gray-50 flex items-center justify-between">
        <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide">
          Visual comparison
        </span>
        {urgencyBadge && (
          <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${urgencyBadge.bg} ${urgencyBadge.text}`}>
            {urgencyBadge.label}
          </span>
        )}
      </div>

      {/* Two-panel layout */}
      <div className="grid grid-cols-2 gap-0 divide-x divide-gray-100">

        {/* Left: uploaded photo */}
        <div className="p-3 flex flex-col gap-2">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
            Your photo
          </p>
          {uploadedImageUrl ? (
            <div className="relative group cursor-zoom-in" onClick={() => setZoomSrc(uploadedImageUrl)}>
              <img
                src={uploadedImageUrl}
                alt="Uploaded clinical photo"
                className="w-full rounded-lg object-cover aspect-square border border-gray-200"
              />
              <div className="absolute inset-0 rounded-lg bg-black/0 group-hover:bg-black/10 transition-all flex items-center justify-center">
                <ZoomIn className="w-5 h-5 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
            </div>
          ) : (
            <div className="w-full aspect-square rounded-lg bg-gray-100 border-2 border-dashed border-gray-300 flex items-center justify-center">
              <p className="text-xs text-gray-400">No photo</p>
            </div>
          )}
        </div>

        {/* Right: reference image */}
        <div className="p-3 flex flex-col gap-2">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
            Reference: {entry?.label || diagnosis}
          </p>
          {refSrc && !refError ? (
            <div className="relative group cursor-zoom-in" onClick={() => setZoomSrc(refSrc)}>
              <img
                src={refSrc}
                alt={`Reference: ${diagnosis}`}
                className="w-full rounded-lg object-cover aspect-square border border-gray-200"
                onError={() => setRefError(true)}
              />
              <div className="absolute inset-0 rounded-lg bg-black/0 group-hover:bg-black/10 transition-all flex items-center justify-center">
                <ZoomIn className="w-5 h-5 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
            </div>
          ) : (
            <div className="aspect-square">
              <PlaceholderImage label={entry?.label || diagnosis} />
            </div>
          )}
        </div>
      </div>

      {/* Key findings to compare */}
      {entry && (
        <div className="px-4 py-3 border-t border-gray-100 bg-gray-50">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
            Key features to look for
          </p>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1">
            {entry.keyFindings.map((f, i) => (
              <div key={i} className="flex items-start gap-1.5 text-xs text-gray-600">
                <span className="mt-1 w-1.5 h-1.5 rounded-full bg-teal-400 flex-shrink-0" />
                {f}
              </div>
            ))}
          </div>
          {entry.caption && (
            <p className="text-xs text-gray-400 italic mt-2 leading-relaxed">
              {entry.caption}
            </p>
          )}
        </div>
      )}

      {/* Zoom overlay */}
      {zoomSrc && <ZoomOverlay src={zoomSrc} onClose={() => setZoomSrc(null)} />}
    </div>
  );
}

// Export the registry so other components can check available keys
export { REFERENCE_LIBRARY };
