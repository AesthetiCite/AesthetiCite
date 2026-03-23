import { useState } from "react";
import {
  Syringe, AlertTriangle, CheckCircle2,
  ChevronDown, ChevronUp, Shield
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

interface DoseResult {
  initial_dose_iu: string;
  repeat_interval: string;
  max_sessions: string;
  technique: string;
  monitoring: string[];
  red_flags: string[];
  evidence_note: string;
}

const REGION_PROTOCOLS: Record<string, DoseResult> = {
  nasolabial_fold: {
    initial_dose_iu: "200–500 IU",
    repeat_interval: "Every 30–60 minutes until reperfusion improves",
    max_sessions: "Repeat as needed — no fixed maximum when active ischemia is present",
    technique: "Inject across the full affected vascular territory, not just the puncture site. Fan technique to cover the region.",
    monitoring: [
      "Reassess capillary refill every 15–30 minutes",
      "Monitor pain, skin colour, and livedo pattern after each cycle",
      "Photograph before and after each treatment cycle",
      "Discontinue when perfusion is restored and stable",
    ],
    red_flags: [
      "Visual disturbance or any ocular symptom — emergency escalation immediately",
      "No improvement after 2–3 treatment cycles",
      "Rapidly expanding livedo pattern beyond initial territory",
      "Progressive darkening or blistering of skin",
    ],
    evidence_note: "Dosing based on expert consensus. Optimal dose and interval are not standardised in RCT evidence. Treat the territory, not the puncture point.",
  },
  lips: {
    initial_dose_iu: "150–300 IU",
    repeat_interval: "Every 30–60 minutes until clinical improvement",
    max_sessions: "Repeat as clinically required",
    technique: "Cover the superior and inferior labial artery territories. Retrograde along the length of the lip if blanching extends.",
    monitoring: [
      "Monitor labial artery territory colour and capillary refill",
      "Reassess every 15–30 minutes",
      "Document product, volume injected, and injection sites",
    ],
    red_flags: [
      "Extension of blanching toward nasal tip or nasolabial fold",
      "Severe escalating pain",
      "Any visual symptom — immediate emergency escalation",
    ],
    evidence_note: "Expert consensus. Labial arteries are superficial — prompt treatment is critical.",
  },
  tear_trough: {
    initial_dose_iu: "75–150 IU",
    repeat_interval: "Every 30–60 minutes",
    max_sessions: "Use conservative doses due to proximity to orbit",
    technique: "Small incremental doses. Avoid periorbital spread — target the infraorbital territory specifically.",
    monitoring: [
      "Monitor infraorbital skin colour and capillary refill closely",
      "Any eyelid oedema or periorbital change requires immediate review",
      "Ophthalmology referral if any visual symptom arises",
    ],
    red_flags: [
      "ANY visual symptom — ophthalmic emergency",
      "Periorbital oedema or skin necrosis",
      "Absence of reperfusion after initial treatment",
    ],
    evidence_note: "Periorbital territory carries highest risk for ophthalmic artery involvement. Low doses and close monitoring.",
  },
  glabella: {
    initial_dose_iu: "300–1500 IU",
    repeat_interval: "Every 30–60 minutes until reperfusion",
    max_sessions: "No maximum — priority is tissue perfusion. Use high doses early.",
    technique: "Glabella is the highest-risk region for retrograde embolism. Treat the supratrochlear and supraorbital territories broadly.",
    monitoring: [
      "Ophthalmology emergency contact must be on standby",
      "Any visual symptom — do not delay emergency services",
      "Monitor full forehead and periorbital territory",
    ],
    red_flags: [
      "ANY visual symptom — call emergency services immediately",
      "Diplopia, ptosis, or any ocular motility change",
      "This is the highest-risk region for permanent vision loss",
    ],
    evidence_note: "Glabellar occlusion carries the highest risk of ophthalmic artery involvement and vision loss. Emergency escalation threshold must be very low.",
  },
  nose: {
    initial_dose_iu: "200–500 IU",
    repeat_interval: "Every 30–60 minutes",
    max_sessions: "Repeat as required — nasal tip ischemia can progress rapidly",
    technique: "Target the columellar and lateral nasal artery territories. The nose has end-artery anatomy — tissue necrosis risk is high.",
    monitoring: [
      "Monitor nasal tip colour and temperature closely",
      "Document progression with serial photography",
      "Low threshold for emergency referral",
    ],
    red_flags: [
      "Darkening of nasal tip — high necrosis risk",
      "Any visual symptom",
      "No response after initial treatment cycle",
    ],
    evidence_note: "Nasal filler carries high tissue necrosis risk due to end-artery anatomy. Aggressive early treatment is preferred.",
  },
  cheek_jaw: {
    initial_dose_iu: "300–600 IU",
    repeat_interval: "Every 30–60 minutes",
    max_sessions: "Repeat as clinically indicated",
    technique: "Cover the facial artery territory for cheek. For jawline, address the inferior labial and submental artery territories.",
    monitoring: [
      "Monitor cheek and perioral skin colour",
      "Reassess capillary refill at 15–30 minute intervals",
      "Extension toward perioral or nasal territory",
      "Any visual symptom",
      "Progressive blanching despite treatment",
    ],
    red_flags: [
      "Extension toward perioral or nasal territory",
      "Any visual symptom",
      "Progressive blanching despite treatment",
    ],
    evidence_note: "Expert consensus. Facial artery territory is large — ensure full territory coverage.",
  },
};

const REGIONS = [
  { value: "nasolabial_fold", label: "Nasolabial fold" },
  { value: "lips",            label: "Lips / perioral" },
  { value: "tear_trough",     label: "Tear trough / infraorbital" },
  { value: "glabella",        label: "Glabella / forehead" },
  { value: "nose",            label: "Nose" },
  { value: "cheek_jaw",       label: "Cheek / jawline" },
];

export function HyaluronidaseCalc() {
  const [region, setRegion] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(false);

  const protocol = region ? REGION_PROTOCOLS[region] : null;

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-2 p-3 rounded-xl border border-red-500/30 bg-red-500/5">
        <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
        <div className="text-sm">
          <span className="font-bold text-red-600 dark:text-red-400">Emergency protocol. </span>
          <span className="text-red-800 dark:text-red-200">
            If any visual symptom is present — stop reading and call emergency services immediately.
            This calculator is for HA filler vascular occlusion only.
          </span>
        </div>
      </div>

      <div className="space-y-1.5">
        <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Injection region
        </label>
        <select
          value={region}
          onChange={(e) => { setRegion(e.target.value); setConfirmed(false); }}
          data-testid="select-region"
          className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
        >
          <option value="">Select region…</option>
          {REGIONS.map((r) => (
            <option key={r.value} value={r.value}>{r.label}</option>
          ))}
        </select>
      </div>

      {region && (
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
            data-testid="checkbox-ha-confirmed"
            className="w-4 h-4 rounded accent-primary"
          />
          <span className="text-sm">I confirm the product is hyaluronic acid filler</span>
        </label>
      )}

      {protocol && confirmed && (
        <div className="space-y-3">

          <Card className="border-red-500/30 bg-red-500/5">
            <CardContent className="p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Syringe className="w-4 h-4 text-red-500" />
                <span className="text-sm font-bold text-red-600 dark:text-red-400">Hyaluronidase dose</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="p-3 rounded-lg bg-background border border-border/60 text-center">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Initial dose</p>
                  <p className="text-lg font-bold text-red-600 dark:text-red-400">{protocol.initial_dose_iu}</p>
                </div>
                <div className="p-3 rounded-lg bg-background border border-border/60 text-center">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Repeat at</p>
                  <p className="text-sm font-semibold">{protocol.repeat_interval}</p>
                </div>
                <div className="p-3 rounded-lg bg-background border border-border/60 text-center">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Max sessions</p>
                  <p className="text-sm font-semibold">{protocol.max_sessions}</p>
                </div>
              </div>
              <div className="p-2.5 rounded-lg bg-background/60 border border-border/50">
                <p className="text-xs text-foreground/80">
                  <span className="font-semibold">Technique: </span>{protocol.technique}
                </p>
              </div>
            </CardContent>
          </Card>

          <Card className="border-red-500/40 bg-red-500/5">
            <CardContent className="p-4 space-y-2">
              <div className="flex items-center gap-2 mb-2">
                <AlertTriangle className="w-4 h-4 text-red-500" />
                <span className="text-xs font-bold text-red-600 dark:text-red-400 uppercase tracking-wider">
                  Red flags — escalate immediately
                </span>
              </div>
              {protocol.red_flags.map((flag, i) => (
                <div key={i} className="flex items-start gap-2 text-sm text-red-800 dark:text-red-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-500 mt-1.5 flex-shrink-0" />
                  {flag}
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4 space-y-2">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Monitoring</span>
              </div>
              {protocol.monitoring.map((item, i) => (
                <div key={i} className="flex items-start gap-2 text-sm text-foreground/80">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mt-1.5 flex-shrink-0" />
                  {item}
                </div>
              ))}
            </CardContent>
          </Card>

          <button
            onClick={() => setEvidenceOpen(!evidenceOpen)}
            className="w-full flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <Shield className="w-3 h-3" />
            Evidence note
            {evidenceOpen
              ? <ChevronUp className="w-3 h-3 ml-auto" />
              : <ChevronDown className="w-3 h-3 ml-auto" />}
          </button>
          {evidenceOpen && (
            <p className="text-xs text-muted-foreground/80 leading-relaxed px-2">
              {protocol.evidence_note}
            </p>
          )}

          <p className="text-[10px] text-muted-foreground/60 text-center leading-relaxed">
            Clinical decision support only. Not a substitute for clinical training, local emergency
            protocols, or manufacturer prescribing information.
          </p>
        </div>
      )}
    </div>
  );
}
