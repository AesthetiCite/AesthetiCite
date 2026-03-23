/**
 * AesthetiCite Tools — Epocrates-grade daily-use clinical calculators
 *
 * What Epocrates does that makes clinicians open it every day:
 *   - Drug dosing lookup: instant, specific, trusted
 *   - Drug interactions: one search, clear result
 *   - Clinical calculators: fast, copy-ready output
 *
 * This page does the same for aesthetic medicine:
 *   Tab 1: Hyaluronidase Calculator  (improved — region + severity + context)
 *   Tab 2: Toxin Dilution            (vial → concentration table)
 *   Tab 3: Toxin Dosing by Region    (unit ranges with evidence notes)
 *   Tab 4: Protocol Lookup           (quick ref card, no LLM latency)
 *   Tab 5: Product Reference         (filler types, properties, risks)
 */

import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Syringe, FlaskConical, BookOpen, Pill, Copy,
  AlertTriangle, ChevronRight, Info, RefreshCw, Calculator,
  CheckCircle2,
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { Link } from "wouter";

// ============================================================================
// TAB 1 — HYALURONIDASE CALCULATOR
// ============================================================================

// Epocrates shows region → dose → notes → repeat interval. We do the same
// but with aesthetic-specific anatomy and vascular occlusion urgency flag.

const HYAL_REGIONS: Record<string, {
  base_iu: number;
  needle: string;
  plane: string;
  notes: string;
  highRisk?: boolean;
}> = {
  "Lips":                { base_iu: 300,  needle: "27–30g", plane: "Submucosal / intradermal", notes: "Fan across vermilion. Multiple small blebs.", highRisk: false },
  "Periorbital / Tear trough": { base_iu: 150, needle: "30g", plane: "Subperiosteal / deep subcutaneous", notes: "Low dose — thin skin. Assess at 48h before repeat.", highRisk: true },
  "Nasolabial folds":    { base_iu: 300,  needle: "27g", plane: "Deep dermis / subdermal", notes: "Linear threading across fold.", highRisk: false },
  "Cheeks / Midface":    { base_iu: 450,  needle: "25–27g", plane: "Submalar / supraperiosteal", notes: "Fan technique. Higher volume may be needed.", highRisk: false },
  "Jawline":             { base_iu: 600,  needle: "25g", plane: "Subdermal / periosteal", notes: "Flood technique for larger depot.", highRisk: false },
  "Chin":                { base_iu: 300,  needle: "27g", plane: "Subdermal", notes: "Circular pattern around chin pad.", highRisk: false },
  "Temple":              { base_iu: 600,  needle: "23–25g", plane: "Subfascial", notes: "Caution: temporal vessels. Aspirate.", highRisk: true },
  "Nose":                { base_iu: 150,  needle: "30g", plane: "Subdermal / supraperiosteal", notes: "Very low dose. High vascular risk zone.", highRisk: true },
  "Forehead / Glabella": { base_iu: 200,  needle: "30g", plane: "Deep subdermal", notes: "High vascular risk. Aspirate.", highRisk: true },
  "Hands":               { base_iu: 300,  needle: "25g", plane: "Subdermal", notes: "Fan across dorsum.", highRisk: false },
  "Neck":                { base_iu: 400,  needle: "25g", plane: "Subdermal", notes: "Grid or serial puncture technique.", highRisk: false },
};

const SEVERITY_MULT: Record<string, number> = {
  "Elective dissolving":        0.5,
  "Mild complication":          0.75,
  "Moderate complication":      1.0,
  "Severe complication":        1.5,
  "Vascular occlusion":         3.0,   // always minimum 1500 IU
};

const CONC_OPTIONS = [
  { label: "150 IU/ml (1:1 saline)", value: 150 },
  { label: "75 IU/ml (1:2 saline)",  value: 75  },
  { label: "450 IU/ml (flood technique)", value: 450 },
];

function HyaluronidaseCalc() {
  const { toast } = useToast();
  const [region, setRegion] = useState("Lips");
  const [severity, setSeverity] = useState("Elective dissolving");
  const [volume, setVolume] = useState("");
  const [concentration, setConcentration] = useState(150);

  const isVO = severity === "Vascular occlusion";
  const regionData = HYAL_REGIONS[region];
  const mult = SEVERITY_MULT[severity] ?? 1.0;

  let baseIU = Math.round(regionData.base_iu * mult);
  if (isVO) baseIU = Math.max(baseIU, 1500);

  // Volume-adjusted dose
  if (volume) {
    const vol = parseFloat(volume);
    if (!isNaN(vol) && vol > 0) {
      const volBased = Math.round(vol * 300);
      baseIU = Math.max(baseIU, volBased);
    }
  }

  const maxIU = isVO ? 10000 : baseIU * 3;
  const mlNeeded = (baseIU / concentration).toFixed(2);
  const repeatInterval = isVO ? "60 minutes if no improvement" : "2 weeks minimum";
  const expectation = isVO
    ? "Blanching should begin to resolve within 30–60 min"
    : "Softening within 24–48h, significant reduction 1–2 weeks";

  const copy = () => {
    const text = [
      `Hyaluronidase — ${region} (${severity})`,
      `Recommended dose: ${baseIU} IU`,
      `Maximum total: ${maxIU} IU`,
      `Volume at ${concentration} IU/ml: ${mlNeeded} ml`,
      `Needle: ${regionData.needle}`,
      `Plane: ${regionData.plane}`,
      `Notes: ${regionData.notes}`,
      `Repeat: ${repeatInterval}`,
    ].join("\n");
    navigator.clipboard.writeText(text);
    toast({ title: "Copied" });
  };

  return (
    <div className="space-y-4 max-w-xl">
      {/* Inputs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <Label className="text-xs">Region</Label>
          <Select value={region} onValueChange={setRegion}>
            <SelectTrigger className="mt-1 h-9 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.keys(HYAL_REGIONS).map((r) => (
                <SelectItem key={r} value={r} className="text-sm">
                  {HYAL_REGIONS[r].highRisk ? "⚠️ " : ""}{r}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div>
          <Label className="text-xs">Indication / Severity</Label>
          <Select value={severity} onValueChange={setSeverity}>
            <SelectTrigger className={`mt-1 h-9 text-sm ${isVO ? "border-red-400" : ""}`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.keys(SEVERITY_MULT).map((s) => (
                <SelectItem key={s} value={s} className="text-sm">{s}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div>
          <Label className="text-xs">Volume of filler injected (ml) — optional</Label>
          <Input
            className="mt-1 h-9 text-sm"
            placeholder="e.g. 1.0"
            value={volume}
            onChange={(e) => setVolume(e.target.value)}
            type="number"
            step="0.1"
            min="0"
          />
        </div>

        <div>
          <Label className="text-xs">Reconstitution concentration</Label>
          <Select value={String(concentration)} onValueChange={(v) => setConcentration(Number(v))}>
            <SelectTrigger className="mt-1 h-9 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CONC_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={String(o.value)} className="text-sm">{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Result card */}
      <Card className={isVO ? "border-red-400 dark:border-red-700" : "border-blue-200 dark:border-blue-800"}>
        <CardContent className="p-4 space-y-3">
          {isVO && (
            <div className="flex items-center gap-2 text-sm font-bold text-red-700 dark:text-red-400">
              <AlertTriangle className="h-4 w-4" />
              VASCULAR OCCLUSION — Act immediately
            </div>
          )}

          {/* Dose display */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-blue-50 dark:bg-blue-950/20 rounded-lg p-3 text-center">
              <p className="text-[10px] text-muted-foreground">Recommended</p>
              <p className={`text-2xl font-bold ${isVO ? "text-red-600" : "text-blue-600"}`}>
                {baseIU.toLocaleString()}
              </p>
              <p className="text-[10px] text-muted-foreground">IU</p>
            </div>
            <div className="bg-muted/50 rounded-lg p-3 text-center">
              <p className="text-[10px] text-muted-foreground">Volume</p>
              <p className="text-2xl font-bold">{mlNeeded}</p>
              <p className="text-[10px] text-muted-foreground">ml</p>
            </div>
            <div className="bg-muted/50 rounded-lg p-3 text-center">
              <p className="text-[10px] text-muted-foreground">Max total</p>
              <p className="text-lg font-bold">{maxIU.toLocaleString()}</p>
              <p className="text-[10px] text-muted-foreground">IU</p>
            </div>
          </div>

          {/* Technical details */}
          <div className="space-y-1.5 text-xs">
            {[
              ["Needle", regionData.needle],
              ["Plane", regionData.plane],
              ["Technique", regionData.notes],
              ["Repeat interval", repeatInterval],
              ["Expected response", expectation],
            ].map(([label, value]) => (
              <div key={label} className="flex gap-2">
                <span className="font-medium w-28 flex-shrink-0">{label}:</span>
                <span className="text-muted-foreground">{value}</span>
              </div>
            ))}
          </div>

          {regionData.highRisk && (
            <div className="flex items-start gap-2 p-2 bg-amber-50 dark:bg-amber-950/20 rounded-lg text-xs text-amber-700 dark:text-amber-400">
              <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" />
              High vascular risk region — aspirate, use smallest effective volume, have emergency protocol ready.
            </div>
          )}

          <Button size="sm" variant="outline" onClick={copy} className="w-full gap-1.5">
            <Copy className="h-3.5 w-3.5" /> Copy dose
          </Button>
        </CardContent>
      </Card>

      <p className="text-[10px] text-muted-foreground">
        Doses are clinical reference ranges. Always follow your training, product IFU, and local protocols.
        For vascular occlusion repeat every 60 min; can use up to 10,000 IU total in severe cases.
      </p>
    </div>
  );
}

// ============================================================================
// TAB 2 — TOXIN DILUTION CALCULATOR
// ============================================================================

const VIAL_SIZES = [50, 100, 200];
const DILUENT_VOLUMES = [1.0, 1.25, 2.0, 2.5, 4.0, 5.0, 10.0];

function ToxinDilutionCalc() {
  const { toast } = useToast();
  const [vialUnits, setVialUnits] = useState(100);
  const [diluent, setDiluent] = useState(2.5);

  const unitsPerMl = vialUnits / diluent;
  const unitsPerPoint1ml = unitsPerMl * 0.1;
  const unitsPerPoint05ml = unitsPerMl * 0.05;

  // Full table: all common volume combinations
  const tableRows = [0.025, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5].map((vol) => ({
    vol,
    units: Math.round(vol * unitsPerMl * 10) / 10,
  }));

  const copy = () => {
    const lines = [
      `Toxin dilution: ${vialUnits}U vial + ${diluent}ml saline`,
      `= ${unitsPerMl.toFixed(1)} units/ml`,
      ``,
      ...tableRows.map((r) => `${r.vol}ml = ${r.units}U`),
    ];
    navigator.clipboard.writeText(lines.join("\n"));
    toast({ title: "Copied" });
  };

  return (
    <div className="space-y-4 max-w-md">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label className="text-xs">Vial size (units)</Label>
          <Select value={String(vialUnits)} onValueChange={(v) => setVialUnits(Number(v))}>
            <SelectTrigger className="mt-1 h-9 text-sm"><SelectValue /></SelectTrigger>
            <SelectContent>
              {VIAL_SIZES.map((v) => (
                <SelectItem key={v} value={String(v)}>{v}U</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-xs">Diluent (ml 0.9% NaCl)</Label>
          <Select value={String(diluent)} onValueChange={(v) => setDiluent(Number(v))}>
            <SelectTrigger className="mt-1 h-9 text-sm"><SelectValue /></SelectTrigger>
            <SelectContent>
              {DILUENT_VOLUMES.map((v) => (
                <SelectItem key={v} value={String(v)}>{v}ml</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Concentration summary */}
      <Card className="border-blue-200 dark:border-blue-800">
        <CardContent className="p-4">
          <div className="flex items-center justify-between mb-3">
            <p className="text-xs text-muted-foreground font-medium">Concentration</p>
            <p className="text-2xl font-bold text-blue-600">{unitsPerMl.toFixed(1)} U/ml</p>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs mb-4">
            <div className="bg-muted/50 rounded-lg p-2 text-center">
              <p className="text-muted-foreground">0.1ml =</p>
              <p className="font-bold text-base">{unitsPerPoint1ml.toFixed(1)}U</p>
            </div>
            <div className="bg-muted/50 rounded-lg p-2 text-center">
              <p className="text-muted-foreground">0.05ml =</p>
              <p className="font-bold text-base">{unitsPerPoint05ml.toFixed(1)}U</p>
            </div>
          </div>

          {/* Dose table */}
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b">
                <th className="text-left py-1 text-muted-foreground font-medium">Volume</th>
                <th className="text-right py-1 text-muted-foreground font-medium">Units</th>
              </tr>
            </thead>
            <tbody>
              {tableRows.map((r) => (
                <tr key={r.vol} className="border-b last:border-0">
                  <td className="py-1.5 font-mono">{r.vol}ml</td>
                  <td className="py-1.5 text-right font-bold">{r.units}U</td>
                </tr>
              ))}
            </tbody>
          </table>

          <Button size="sm" variant="outline" onClick={copy} className="w-full mt-3 gap-1.5">
            <Copy className="h-3.5 w-3.5" /> Copy table
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

// ============================================================================
// TAB 3 — TOXIN DOSING BY REGION
// ============================================================================

const TOXIN_DOSING: {
  region: string;
  botox: string;
  dysport: string;
  notes: string;
  danger?: string;
}[] = [
  { region: "Glabella (frown lines)", botox: "15–25U", dysport: "45–75U", notes: "3–5 injection points. Avoid < 1cm above brow. Highest ptosis risk zone.", danger: "Ptosis, brow asymmetry" },
  { region: "Forehead", botox: "6–15U", dysport: "18–45U", notes: "Always treat with glabella. Avoid in low brow. 4–6 points.", danger: "Brow drop" },
  { region: "Crow's feet (lateral canthal)", botox: "6–15U per side", dysport: "15–30U per side", notes: "3 points lateral to orbital rim. Stay > 1cm from orbital rim.", danger: "Lower lid ectropion" },
  { region: "Upper lip (lip flip)", botox: "2–4U", dysport: "6–12U", notes: "4 points into orbicularis oris. Low dose — functional muscle.", danger: "Speech, straw difficulty" },
  { region: "Platysmal bands", botox: "25–50U total", dysport: "75–150U total", notes: "Serial injections along bands. 2.5U per point.", danger: "Dysphagia (if deep)" },
  { region: "Masseter (bruxism/jaw)", botox: "20–40U per side", dysport: "60–120U per side", notes: "Lower third of masseter only. Avoid parotid overlap.", danger: "Smile asymmetry, paradoxical bulge" },
  { region: "Hyperhidrosis axilla", botox: "50–100U per axilla", dysport: "150–300U per axilla", notes: "Grid pattern 1–2cm apart. Minor starch-iodine test first.", danger: "Compensatory sweating" },
  { region: "Bunny lines (nasalis)", botox: "2–5U per side", dysport: "6–15U per side", notes: "1–2 points per side on nasal sidewall.", danger: "Nasal flare loss" },
  { region: "Chin (mentalis dimpling)", botox: "4–8U", dysport: "12–24U", notes: "1–2 central points. Avoid lateral placement.", danger: "Chin asymmetry" },
  { region: "Brow lift", botox: "2–4U per side", dysport: "6–12U per side", notes: "Lateral orbicularis oculi above brow tail only.", danger: "Lateral brow drop" },
];

function ToxinDosingTable() {
  const { toast } = useToast();
  const [brand, setBrand] = useState<"botox" | "dysport">("botox");
  const [search, setSearch] = useState("");

  const filtered = TOXIN_DOSING.filter((r) =>
    r.region.toLowerCase().includes(search.toLowerCase())
  );

  const copy = (row: typeof TOXIN_DOSING[0]) => {
    const dose = brand === "botox" ? row.botox : row.dysport;
    navigator.clipboard.writeText(`${row.region}: ${dose}\n${row.notes}`);
    toast({ title: "Copied" });
  };

  return (
    <div className="space-y-3 max-w-2xl">
      <div className="flex gap-2 items-center">
        <div className="flex rounded-lg border overflow-hidden">
          {(["botox", "dysport"] as const).map((b) => (
            <button
              key={b}
              type="button"
              onClick={() => setBrand(b)}
              className={`px-4 py-1.5 text-xs font-medium capitalize transition-colors ${
                brand === b ? "bg-blue-600 text-white" : "hover:bg-muted"
              }`}
            >
              {b === "botox" ? "Botox / Bocouture / Xeomin" : "Dysport / Azzalure"}
            </button>
          ))}
        </div>
        <Input
          className="h-8 text-xs flex-1"
          placeholder="Filter region…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="space-y-2">
        {filtered.map((row) => (
          <Card key={row.region}>
            <CardContent className="p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <p className="text-sm font-medium">{row.region}</p>
                    <Badge variant="outline" className="text-xs bg-blue-50 dark:bg-blue-950/20 text-blue-700 dark:text-blue-300 border-blue-200">
                      {brand === "botox" ? row.botox : row.dysport}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground">{row.notes}</p>
                  {row.danger && (
                    <p className="text-xs text-amber-600 dark:text-amber-400 mt-0.5">
                      ⚠️ Watch: {row.danger}
                    </p>
                  )}
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 w-7 p-0 flex-shrink-0"
                  onClick={() => copy(row)}
                >
                  <Copy className="h-3.5 w-3.5" />
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <p className="text-[10px] text-muted-foreground">
        Dose ranges are clinical reference. Individual patient anatomy, product-specific IFU, and
        clinical training determine actual dosing. Dysport:Botox ratio approximately 3:1 for most indications.
      </p>
    </div>
  );
}

// ============================================================================
// TAB 4 — PROTOCOL QUICK LOOKUP
// ============================================================================

const PROTOCOLS: Record<string, {
  name: string;
  urgency: "immediate" | "urgent" | "same_day" | "routine";
  summary: string;
  steps: string[];
  keyDrug?: string;
  escalation: string;
}> = {
  vascular_occlusion: {
    name: "Vascular Occlusion",
    urgency: "immediate",
    summary: "Blanching or livedo after HA filler injection. Time-critical — 60-minute window.",
    steps: [
      "Stop injection immediately",
      "Warm compress to affected area",
      "Hyaluronidase 1500 IU — flood the region NOW",
      "Aspirin 300mg orally (unless contraindicated)",
      "Nitroglycerin paste 2% topically",
      "Monitor capillary refill every 5 minutes",
      "Repeat hyaluronidase at 60 min if no improvement",
      "Check visual symptoms — ANY visual change → 999 now",
    ],
    keyDrug: "Hyaluronidase 1500–3000 IU minimum",
    escalation: "No improvement at 60 min → emergency department. Any visual symptom → 999 + ophthalmology immediately.",
  },
  anaphylaxis: {
    name: "Anaphylaxis",
    urgency: "immediate",
    summary: "Urticaria, wheeze, hypotension, or angioedema after injectable treatment.",
    steps: [
      "Call 999 immediately",
      "Adrenaline 0.5mg IM into lateral thigh",
      "Lay flat — legs elevated (unless airway compromise)",
      "High-flow oxygen 15L/min",
      "Repeat adrenaline every 5 min if no improvement",
      "Chlorphenamine 10mg IM/IV (adjunct only)",
      "Hydrocortisone 200mg IV/IM (adjunct only)",
    ],
    keyDrug: "Adrenaline 1:1000, 0.5mg IM — first line",
    escalation: "Emergency services already called. Maintain airway. Be ready to perform CPR.",
  },
  ptosis: {
    name: "Botox-Induced Ptosis",
    urgency: "routine",
    summary: "Eyelid or brow drop 1–14 days post-botulinum toxin. Temporary — resolves 4–8 weeks.",
    steps: [
      "Reassure patient — almost always temporary",
      "Measure MRD1 (margin-reflex distance) at baseline",
      "Apraclonidine 0.5% eye drops 1–2 drops, 3x daily",
      "Avoid massage or heat to toxin area",
      "Review at 2 weeks",
      "Ophthalmology if not improving by 8 weeks or diplopia present",
    ],
    keyDrug: "Apraclonidine 0.5% eye drops — raises lid 1–2mm",
    escalation: "Diplopia or ophthalmoplegia → urgent ophthalmology.",
  },
  infection: {
    name: "Post-Filler Infection / Biofilm",
    urgency: "urgent",
    summary: "Erythema, warmth, pain, or pus after filler treatment. Distinguish early cellulitis from abscess from biofilm.",
    steps: [
      "Assess: cellulitis vs abscess vs biofilm",
      "If abscess: incise, drain, swab for MC&S",
      "Start antibiotics: co-amoxiclav 625mg TDS (or clarithromycin if penicillin allergy)",
      "If biofilm suspected: dual therapy — clarithromycin 500mg BD + ciprofloxacin 500mg BD × 4–6 weeks",
      "If HA filler: consider hyaluronidase 1500 IU to remove substrate",
      "If systemic signs or no improvement at 48h → A&E or hospital",
    ],
    keyDrug: "Co-amoxiclav 625mg TDS or dual biofilm therapy",
    escalation: "Fever + spreading erythema + unwell → A&E same day.",
  },
  nodule: {
    name: "Filler Nodule / Granuloma",
    urgency: "same_day",
    summary: "Firm or tender lump at injection site. Distinguish non-inflammatory from inflammatory from biofilm.",
    steps: [
      "Assess timing: early (<4 wks) vs late (>4 wks)",
      "If HA filler: hyaluronidase 75–150 IU intralesional",
      "If inflammatory: 5-FU 50mg/ml + triamcinolone 40mg/ml 1:1 mix, 0.1–0.2ml per nodule",
      "If late/hard/recurrent: consider biofilm protocol",
      "Review at 4 weeks",
    ],
    keyDrug: "Hyaluronidase 75–150 IU OR 5-FU + triamcinolone mix",
    escalation: "No improvement at 8 weeks → dermatology or plastic surgery.",
  },
  dir: {
    name: "Delayed Inflammatory Reaction",
    urgency: "same_day",
    summary: "Bilateral swelling 2+ weeks post-treatment, often triggered by systemic illness, vaccine, or virus.",
    steps: [
      "Confirm timing: 2+ weeks post-procedure",
      "Identify trigger if possible (illness, dental work, vaccination)",
      "Cetirizine 10mg daily (first line)",
      "If severe: prednisolone 30mg reducing over 5–7 days",
      "For recurrent DIR: hydroxychloroquine 200mg BD (review with rheumatology)",
      "Consider dissolving if recurrent or severe",
    ],
    keyDrug: "Cetirizine 10mg OR prednisolone burst",
    escalation: "Airway involvement or anaphylaxis features → emergency services.",
  },
};

const URGENCY_STYLES = {
  immediate: "border-red-500 bg-red-50 dark:bg-red-950/20",
  urgent:    "border-orange-400 bg-orange-50 dark:bg-orange-950/20",
  same_day:  "border-amber-400 bg-amber-50 dark:bg-amber-950/20",
  routine:   "border-blue-200 bg-blue-50 dark:bg-blue-950/20",
};

const URGENCY_BADGE = {
  immediate: "bg-red-600 text-white",
  urgent:    "bg-orange-500 text-white",
  same_day:  "bg-amber-500 text-white",
  routine:   "bg-blue-500 text-white",
};

function ProtocolLookup() {
  const { toast } = useToast();
  const [selected, setSelected] = useState<string>("vascular_occlusion");
  const protocol = PROTOCOLS[selected];

  const copy = () => {
    const text = [
      `PROTOCOL: ${protocol.name}`,
      `URGENCY: ${protocol.urgency.toUpperCase()}`,
      `SUMMARY: ${protocol.summary}`,
      ``,
      `STEPS:`,
      ...protocol.steps.map((s, i) => `${i + 1}. ${s}`),
      ``,
      `KEY DRUG: ${protocol.keyDrug}`,
      `ESCALATION: ${protocol.escalation}`,
    ].join("\n");
    navigator.clipboard.writeText(text);
    toast({ title: "Protocol copied" });
  };

  return (
    <div className="space-y-3 max-w-xl">
      {/* Protocol selector */}
      <div className="flex flex-wrap gap-2">
        {Object.entries(PROTOCOLS).map(([key, p]) => (
          <button
            key={key}
            type="button"
            onClick={() => setSelected(key)}
            className={`px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors ${
              selected === key
                ? "border-blue-500 bg-blue-50 dark:bg-blue-950/30 text-blue-700 dark:text-blue-300"
                : "border-border hover:border-blue-400"
            }`}
          >
            {p.name}
          </button>
        ))}
      </div>

      {/* Protocol card */}
      {protocol && (
        <Card className={`border-2 ${URGENCY_STYLES[protocol.urgency]}`}>
          <CardHeader className="pb-2 pt-3 px-4">
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="text-sm">{protocol.name}</CardTitle>
              <Badge className={`text-[11px] ${URGENCY_BADGE[protocol.urgency]}`}>
                {protocol.urgency.replace("_", " ").toUpperCase()}
              </Badge>
            </div>
            <CardDescription className="text-xs">{protocol.summary}</CardDescription>
          </CardHeader>
          <CardContent className="px-4 pb-4 space-y-3">
            <ol className="space-y-1.5">
              {protocol.steps.map((step, i) => (
                <li key={i} className="flex items-start gap-2 text-sm">
                  <span className="flex-shrink-0 w-5 h-5 rounded-full bg-muted flex items-center justify-center text-[10px] font-bold text-muted-foreground mt-0.5">
                    {i + 1}
                  </span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>

            {protocol.keyDrug && (
              <div className="flex items-start gap-2 p-2.5 bg-blue-50 dark:bg-blue-950/20 rounded-lg text-xs">
                <Syringe className="h-3.5 w-3.5 text-blue-500 flex-shrink-0 mt-0.5" />
                <span className="font-medium">{protocol.keyDrug}</span>
              </div>
            )}

            <div className="flex items-start gap-2 p-2.5 bg-red-50 dark:bg-red-950/20 rounded-lg text-xs text-red-700 dark:text-red-400">
              <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" />
              <span>{protocol.escalation}</span>
            </div>

            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={copy} className="flex-1 gap-1.5">
                <Copy className="h-3.5 w-3.5" /> Copy Protocol
              </Button>
              <Link href={`/decide?complication=${encodeURIComponent(protocol.name)}`}>
                <Button size="sm" variant="outline" className="gap-1.5">
                  <ChevronRight className="h-3.5 w-3.5" /> Full Protocol
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ============================================================================
// TAB 5 — PRODUCT REFERENCE
// ============================================================================

const FILLERS = [
  { brand: "Juvederm Ultra", ha: true, crosslink: "Medium", duration: "6–12 months", viscosity: "Medium-Low", indication: "Lips, perioral, superficial lines", risk: "Tyndall if superficial. Moderate VO risk." },
  { brand: "Juvederm Voluma", ha: true, crosslink: "High", duration: "18–24 months", viscosity: "High", indication: "Cheeks, midface, chin", risk: "Vascular occlusion risk. Deep placement." },
  { brand: "Juvederm Volux", ha: true, crosslink: "Very High", duration: "18–24 months", viscosity: "Very High", indication: "Jawline, chin projection", risk: "High risk if superficial — stays in deep plane." },
  { brand: "Restylane", ha: true, crosslink: "Medium", duration: "6–12 months", viscosity: "Medium", indication: "Lips, nasolabial, tear trough", risk: "Moderate VO risk. Lower Tyndall than Juvederm." },
  { brand: "Teosyal RHA 4", ha: true, crosslink: "Resilient HA", duration: "12–18 months", viscosity: "High", indication: "Deep structural, cheeks", risk: "Dynamic movement areas. Deep placement." },
  { brand: "Belotero Balance", ha: true, crosslink: "Low", duration: "6–9 months", viscosity: "Low", indication: "Fine lines, superficial", risk: "Low Tyndall risk. Avoid deep placement." },
  { brand: "Sculptra", ha: false, crosslink: "n/a", duration: "18–24 months", viscosity: "Liquid (PLLA)", indication: "Volume restoration, collagen stimulator", risk: "Nodules (dilution critical). Delayed onset." },
  { brand: "Radiesse", ha: false, crosslink: "n/a", duration: "12–18 months", viscosity: "High (CaHA)", indication: "Deep tissue, hands, jawline", risk: "Not dissolvable. Arterial injection risk." },
];

function ProductReference() {
  const [search, setSearch] = useState("");
  const filtered = FILLERS.filter(
    (f) => f.brand.toLowerCase().includes(search.toLowerCase()) ||
           f.indication.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-3 max-w-2xl">
      <div className="flex gap-2 items-center">
        <Input
          className="h-8 text-xs flex-1"
          placeholder="Search product or indication…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="flex gap-2 text-xs">
          <Badge variant="outline" className="text-[10px] bg-blue-50 border-blue-200 text-blue-700">🟦 HA</Badge>
          <Badge variant="outline" className="text-[10px] bg-orange-50 border-orange-200 text-orange-700">🟧 Non-HA</Badge>
        </div>
      </div>

      <div className="space-y-2">
        {filtered.map((f) => (
          <Card key={f.brand} className={f.ha ? "" : "border-orange-200 dark:border-orange-900"}>
            <CardContent className="p-3">
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-semibold">{f.brand}</p>
                  {f.ha
                    ? <Badge variant="outline" className="text-[10px] bg-blue-50 border-blue-200 text-blue-700">HA</Badge>
                    : <Badge variant="outline" className="text-[10px] bg-orange-50 border-orange-200 text-orange-700">Non-HA</Badge>
                  }
                </div>
                <span className="text-xs text-muted-foreground">{f.duration}</span>
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs">
                <div><span className="text-muted-foreground">Indication: </span>{f.indication}</div>
                <div><span className="text-muted-foreground">Viscosity: </span>{f.viscosity}</div>
                <div className="col-span-2 text-amber-700 dark:text-amber-400 mt-1">
                  ⚠️ {f.risk}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <p className="text-[10px] text-muted-foreground">
        Product data is clinical reference. Always verify against current manufacturer IFU and product SmPC.
        Non-HA fillers cannot be dissolved with hyaluronidase.
      </p>
    </div>
  );
}

// ============================================================================
// ROOT PAGE
// ============================================================================

export default function ToolsPage() {
  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b bg-background/95 backdrop-blur-sm sticky top-0 z-30">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center gap-3">
          <Calculator className="h-5 w-5 text-blue-500 flex-shrink-0" />
          <div>
            <h1 className="font-semibold text-sm">Clinical Tools</h1>
            <p className="text-xs text-muted-foreground hidden sm:block">
              Dosing calculators · Protocol lookup · Product reference
            </p>
          </div>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-4 py-6">
        <Tabs defaultValue="hyaluronidase">
          <TabsList className="mb-6 flex-wrap h-auto gap-1">
            <TabsTrigger value="hyaluronidase" className="text-xs gap-1.5">
              <Syringe className="h-3.5 w-3.5" /> Hyaluronidase
            </TabsTrigger>
            <TabsTrigger value="dilution" className="text-xs gap-1.5">
              <FlaskConical className="h-3.5 w-3.5" /> Toxin Dilution
            </TabsTrigger>
            <TabsTrigger value="dosing" className="text-xs gap-1.5">
              <Calculator className="h-3.5 w-3.5" /> Toxin Dosing
            </TabsTrigger>
            <TabsTrigger value="protocols" className="text-xs gap-1.5">
              <BookOpen className="h-3.5 w-3.5" /> Protocols
            </TabsTrigger>
            <TabsTrigger value="products" className="text-xs gap-1.5">
              <Pill className="h-3.5 w-3.5" /> Products
            </TabsTrigger>
          </TabsList>

          <TabsContent value="hyaluronidase">
            <div className="mb-4">
              <h2 className="font-medium text-sm">Hyaluronidase Dosing Calculator</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Region + indication → recommended dose, volume, technique
              </p>
            </div>
            <HyaluronidaseCalc />
          </TabsContent>

          <TabsContent value="dilution">
            <div className="mb-4">
              <h2 className="font-medium text-sm">Toxin Dilution Calculator</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Vial size + saline volume → concentration table
              </p>
            </div>
            <ToxinDilutionCalc />
          </TabsContent>

          <TabsContent value="dosing">
            <div className="mb-4">
              <h2 className="font-medium text-sm">Toxin Dosing by Region</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Evidence-based unit ranges per region — Botox and Dysport
              </p>
            </div>
            <ToxinDosingTable />
          </TabsContent>

          <TabsContent value="protocols">
            <div className="mb-4">
              <h2 className="font-medium text-sm">Quick Protocol Lookup</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Step-by-step complication protocols — no search latency
              </p>
            </div>
            <ProtocolLookup />
          </TabsContent>

          <TabsContent value="products">
            <div className="mb-4">
              <h2 className="font-medium text-sm">Filler Product Reference</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                HA and non-HA fillers — properties, indications, risks
              </p>
            </div>
            <ProductReference />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
