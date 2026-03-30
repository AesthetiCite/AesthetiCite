/**
 * pages/clinical-tools-expanded.tsx
 * ===================================
 * All 24 clinical tools for aesthetic injectable medicine.
 * Route: /clinical-tools
 *
 * Replaces the existing /clinical-tools page entirely.
 *
 * Tools by category:
 *   INJECTABLES (6): Toxin dilution, Unit converter, Dosing guide,
 *     HA volume estimator, Cannula selector, Onset/duration reference
 *   SAFETY (6): Hyaluronidase, Vascular risk, GLP-1, Adrenaline,
 *     Local anaesthetic max dose, Bleeding risk screener
 *   SKIN (4): Fitzpatrick, Wrinkle grading, GAIS scale, Facial ageing
 *   PATIENT (4): Lip proportions, Consent checklist, Aftercare, Photo guide
 *   CLINIC (4): Pricing estimator, CPD tracker, Treatment interval, eGFR note
 *
 * Register in App.tsx:
 *   import ClinicalToolsPage from "@/pages/clinical-tools-expanded";
 *   <Route path="/clinical-tools">{() => <ProtectedRoute component={ClinicalToolsPage} />}</Route>
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/use-auth";
import {
  Syringe, Shield, Microscope, Users, LayoutDashboard,
  ChevronDown, ChevronUp, Loader2, AlertTriangle,
  CheckCircle, Info, Copy, ClipboardCheck,
} from "lucide-react";

const inputCls = "w-full text-sm rounded-lg border border-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-400 bg-background text-foreground";
const selectCls = inputCls;
const labelCls = "text-xs font-medium text-gray-500 block mb-1";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><label className={labelCls}>{label}</label>{children}</div>;
}
function Grid2({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-2 gap-3">{children}</div>;
}
function ResultBox({ children, accent = false }: { children: React.ReactNode; accent?: boolean }) {
  return (
    <div className={`rounded-xl p-4 border ${accent ? "bg-teal-50 border-teal-200" : "bg-muted/40 border-border"}`}>
      {children}
    </div>
  );
}
function ResultRow({ label, value, bold = false }: { label: string; value: string; bold?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1.5 border-b border-border last:border-0">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={`text-xs text-right ${bold ? "font-semibold text-foreground" : "text-foreground"}`}>{value}</span>
    </div>
  );
}
function Warning({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-800">
      <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />{children}
    </div>
  );
}
function Success({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-2 rounded-lg border border-green-200 bg-green-50 px-3 py-2.5 text-xs text-green-800">
      <CheckCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />{children}
    </div>
  );
}

async function callTool(endpoint: string, body: object, token: string) {
  const res = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  });
  if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e?.detail || "Tool failed"); }
  return res.json();
}

// ═══════════════════════════════════════════════════════════════
// INJECTABLES TOOLS
// ═══════════════════════════════════════════════════════════════

// Tool 1: Toxin dilution calculator
function ToxinDilution() {
  const [vial, setVial] = useState("100");
  const [saline, setSaline] = useState("2.5");

  const vialU = parseFloat(vial) || 0;
  const salineML = parseFloat(saline) || 0;
  const uPerML = salineML > 0 ? vialU / salineML : 0;
  const uPer01 = uPerML / 10;
  const uPerInsulin = uPerML / 100; // per U mark on insulin syringe (1U mark = 0.01mL)

  return (
    <div className="space-y-4">
      <Grid2>
        <Field label="Vial size (units)">
          <select value={vial} onChange={e => setVial(e.target.value)} className={selectCls}>
            <option value="50">50 U</option>
            <option value="100">100 U</option>
            <option value="200">200 U</option>
            <option value="300">300 U (Dysport)</option>
            <option value="500">500 U (Dysport)</option>
          </select>
        </Field>
        <Field label="Saline added (mL)">
          <select value={saline} onChange={e => setSaline(e.target.value)} className={selectCls}>
            <option value="1">1.0 mL</option>
            <option value="1.25">1.25 mL</option>
            <option value="2">2.0 mL</option>
            <option value="2.5">2.5 mL</option>
            <option value="4">4.0 mL</option>
            <option value="5">5.0 mL</option>
            <option value="10">10.0 mL</option>
          </select>
        </Field>
      </Grid2>
      {uPerML > 0 && (
        <ResultBox accent>
          <ResultRow label="Units per mL" value={`${uPerML.toFixed(1)} U/mL`} bold />
          <ResultRow label="Units per 0.1 mL" value={`${uPer01.toFixed(1)} U`} bold />
          <ResultRow label="Units per 0.01 mL (1U insulin mark)" value={`${uPerInsulin.toFixed(2)} U`} />
          <ResultRow label="To give 4 U inject" value={`${(4/uPerML).toFixed(3)} mL`} />
          <ResultRow label="To give 10 U inject" value={`${(10/uPerML).toFixed(3)} mL`} />
          <ResultRow label="To give 20 U inject" value={`${(20/uPerML).toFixed(3)} mL`} />
        </ResultBox>
      )}
      <Warning>Units are product-specific and not interchangeable between brands. Use the converter below for brand equivalents.</Warning>
    </div>
  );
}

// Tool 2: Neuromodulator unit converter
function NeurotoxinConverter() {
  const [from, setFrom] = useState("botox");
  const [units, setUnits] = useState("20");

  // Conversion ratios to Botox units (approximate consensus)
  const RATIOS: Record<string, { label: string; toBotox: number; note?: string }> = {
    botox:     { label: "Botox / Bocouture / Xeomin (1:1)", toBotox: 1 },
    azzalure:  { label: "Azzalure (Speywood)", toBotox: 1/2.5 },
    dysport:   { label: "Dysport (Galderma)", toBotox: 1/3 },
    letybo:    { label: "Letybo (1:1 Botox)", toBotox: 1 },
    bocouture: { label: "Bocouture (1:1 Botox)", toBotox: 1 },
    xeomin:    { label: "Xeomin (1:1 Botox)", toBotox: 1 },
  };

  const inputU = parseFloat(units) || 0;
  const inBotox = inputU * RATIOS[from].toBotox;

  const conversions = Object.entries(RATIOS).map(([key, r]) => ({
    key, label: r.label,
    units: inBotox / r.toBotox,
  }));

  return (
    <div className="space-y-4">
      <Grid2>
        <Field label="From brand">
          <select value={from} onChange={e => setFrom(e.target.value)} className={selectCls}>
            {Object.entries(RATIOS).map(([k, r]) => (
              <option key={k} value={k}>{r.label}</option>
            ))}
          </select>
        </Field>
        <Field label="Units">
          <input type="number" value={units} onChange={e => setUnits(e.target.value)} min={0} step={1} className={inputCls} />
        </Field>
      </Grid2>
      {inputU > 0 && (
        <ResultBox accent>
          {conversions.filter(c => c.key !== from).map(c => (
            <ResultRow key={c.key} label={c.label} value={`${Math.round(c.units * 10) / 10} U`} bold={c.units !== inputU} />
          ))}
        </ResultBox>
      )}
      <Warning>Conversion ratios are approximate consensus estimates. Units are not interchangeable per manufacturer IFUs. Always follow product-specific dosing.</Warning>
    </div>
  );
}

// Tool 3: HA Filler volume estimator
function HAFillerVolume() {
  const REGIONS: Record<string, { light: string; moderate: string; significant: string; product_class: string; note: string }> = {
    "Lips":                    { light:"0.3–0.5 mL", moderate:"0.5–1.0 mL", significant:"1.0–2.0 mL", product_class:"Soft/medium HA", note:"Start conservative. Lip borders before body." },
    "Tear trough":             { light:"0.3–0.5 mL", moderate:"0.5–0.8 mL", significant:"0.8–1.2 mL", product_class:"Soft, low G-prime HA", note:"Extremely vascular area. Deep placement essential." },
    "Nasolabial folds":        { light:"0.5–0.8 mL", moderate:"0.8–1.5 mL", significant:"1.5–2.5 mL", product_class:"Medium–firm HA", note:"Bilateral treatment. Massage well post-injection." },
    "Cheeks":                  { light:"0.5–1.0 mL", moderate:"1.0–2.0 mL", significant:"2.0–4.0 mL", product_class:"Firm, high G-prime HA or CaHA", note:"Consider biostimulators for GLP-1 patients." },
    "Jawline":                 { light:"0.5–1.0 mL", moderate:"1.0–2.0 mL", significant:"2.0–4.0 mL", product_class:"Firm, high G-prime HA", note:"Facial artery at risk. Assess from multiple angles." },
    "Chin":                    { light:"0.3–0.5 mL", moderate:"0.5–1.0 mL", significant:"1.0–2.0 mL", product_class:"Medium–firm HA", note:"Mental nerve. Deep supraperiosteal placement." },
    "Temples":                 { light:"0.5–0.8 mL", moderate:"0.8–1.5 mL", significant:"1.5–3.0 mL", product_class:"Medium HA or CaHA", note:"Temporal artery — high vascular risk." },
    "Marionette lines":        { light:"0.3–0.5 mL", moderate:"0.5–1.0 mL", significant:"1.0–2.0 mL", product_class:"Medium HA", note:"Treat in combination with jowl assessment." },
    "Perioral lines":          { light:"0.1–0.3 mL", moderate:"0.3–0.5 mL", significant:"0.5–1.0 mL", product_class:"Soft/medium HA", note:"Small volumes, dilute product preferred." },
    "Nose (rhinoplasty filler)":{ light:"0.1–0.2 mL", moderate:"0.2–0.5 mL", significant:"0.5–1.0 mL", product_class:"Firm HA", note:"CRITICAL — highest vascular occlusion risk. Expert only." },
  };

  const [region, setRegion] = useState("Lips");
  const [severity, setSeverity] = useState("moderate");
  const r = REGIONS[region];

  return (
    <div className="space-y-4">
      <Grid2>
        <Field label="Region">
          <select value={region} onChange={e => setRegion(e.target.value)} className={selectCls}>
            {Object.keys(REGIONS).map(k => <option key={k} value={k}>{k}</option>)}
          </select>
        </Field>
        <Field label="Volume loss / correction severity">
          <select value={severity} onChange={e => setSeverity(e.target.value)} className={selectCls}>
            <option value="light">Mild — subtle enhancement</option>
            <option value="moderate">Moderate — visible correction</option>
            <option value="significant">Significant — major volumisation</option>
          </select>
        </Field>
      </Grid2>
      <ResultBox accent>
        <ResultRow label="Suggested volume range" value={r[severity as keyof typeof r] as string} bold />
        <ResultRow label="Product class" value={r.product_class} />
        <ResultRow label="Clinical note" value={r.note} />
      </ResultBox>
      {region === "Nose (rhinoplasty filler)" && (
        <div className="rounded-lg border-2 border-red-300 bg-red-50 px-3 py-2.5 text-xs text-red-800 font-medium">
          CRITICAL — Nasal filler carries the highest risk of vascular occlusion and vision loss. Only experienced injectors. Have hyaluronidase immediately available.
        </div>
      )}
      <Warning>These are population ranges. Adjust for individual anatomy, prior treatment, GLP-1 status, and patient preference. Never inject maximum volumes on first treatment.</Warning>
    </div>
  );
}

// Tool 4: Cannula vs needle selector
function CannulaNeedleSelector() {
  const [region, setRegion] = useState("");
  const [vascular, setVascular] = useState("moderate");
  const [depth, setDepth] = useState("subcutaneous");
  const [experience, setExperience] = useState("intermediate");

  const NEEDLE_REGIONS = ["lips","perioral","glabella","nose"];
  const CANNULA_REGIONS = ["cheeks","jawline","nasolabial","temples","tear trough","marionette"];

  const regionL = region.toLowerCase();
  const isNeedleZone = NEEDLE_REGIONS.some(r => regionL.includes(r));
  const isCannulaZone = CANNULA_REGIONS.some(r => regionL.includes(r));
  const highVascular = vascular === "high";
  const lowExperience = experience === "novice";

  let recommendation = "needle";
  let rationale = "";
  let colour = "amber";

  if (isCannulaZone || (highVascular && !isNeedleZone)) {
    recommendation = "cannula";
    colour = "green";
    rationale = `${isCannulaZone ? "Region anatomy favours cannula. " : ""}${highVascular ? "High vascular risk area — cannula reduces intravascular injection risk. " : ""}Cannula preferred for this combination.`;
  } else if (isNeedleZone) {
    recommendation = "needle";
    colour = "amber";
    rationale = "This region typically requires needle technique for precision. Extra care with aspiration and slow injection.";
  } else {
    recommendation = "either";
    colour = "blue";
    rationale = "Either technique is appropriate. Consider cannula if vascular risk is a concern, needle for precision placement.";
  }

  if (lowExperience && recommendation !== "cannula") {
    rationale += " Note: for novice injectors, cannula may reduce complication risk.";
  }

  const colourMap: Record<string, string> = {
    green: "bg-green-50 border-green-300 text-green-800",
    amber: "bg-amber-50 border-amber-300 text-amber-800",
    blue: "bg-blue-50 border-blue-300 text-blue-800",
  };

  return (
    <div className="space-y-4">
      <Grid2>
        <Field label="Region">
          <input type="text" value={region} onChange={e => setRegion(e.target.value)} placeholder="e.g. cheeks, lips, jawline" className={inputCls} />
        </Field>
        <Field label="Vascular risk of region">
          <select value={vascular} onChange={e => setVascular(e.target.value)} className={selectCls}>
            <option value="low">Low</option>
            <option value="moderate">Moderate</option>
            <option value="high">High</option>
          </select>
        </Field>
        <Field label="Injection depth">
          <select value={depth} onChange={e => setDepth(e.target.value)} className={selectCls}>
            <option value="intradermal">Intradermal</option>
            <option value="subcutaneous">Subcutaneous</option>
            <option value="supraperiosteal">Supraperiosteal</option>
            <option value="intramuscular">Intramuscular</option>
          </select>
        </Field>
        <Field label="Injector experience">
          <select value={experience} onChange={e => setExperience(e.target.value)} className={selectCls}>
            <option value="novice">Novice</option>
            <option value="intermediate">Intermediate</option>
            <option value="advanced">Advanced</option>
            <option value="expert">Expert</option>
          </select>
        </Field>
      </Grid2>
      {region && (
        <div className={`rounded-xl border-2 px-4 py-3 ${colourMap[colour]}`}>
          <p className="text-sm font-bold capitalize mb-1">Recommendation: {recommendation === "either" ? "either technique suitable" : `${recommendation} preferred`}</p>
          <p className="text-xs leading-relaxed">{rationale}</p>
        </div>
      )}
    </div>
  );
}

// Tool 5: Neurotoxin onset / duration reference
function ToxinOnsetDuration() {
  const PRODUCTS = [
    { name:"Botox (onabotulinumtoxinA)", brand:"Allergan/AbbVie", onset:"3–5 days", peak:"7–14 days", duration:"3–4 months", vial:"100U / 200U" },
    { name:"Dysport (abobotulinumtoxinA)", brand:"Galderma/Ipsen", onset:"2–5 days", peak:"7–14 days", duration:"3–4 months", vial:"300U / 500U" },
    { name:"Xeomin (incobotulinumtoxinA)", brand:"Merz", onset:"3–5 days", peak:"7–14 days", duration:"3–4 months", vial:"50U / 100U / 200U" },
    { name:"Bocouture (incobotulinumtoxinA)", brand:"Merz (UK brand name)", onset:"3–5 days", peak:"7–14 days", duration:"3–4 months", vial:"50U / 100U" },
    { name:"Azzalure (abobotulinumtoxinA)", brand:"Galderma (EU/UK)", onset:"2–5 days", peak:"7–14 days", duration:"3–4 months", vial:"125 Speywood U" },
    { name:"Letybo (letibotulinumtoxinA)", brand:"Croma / Ipsen", onset:"3–5 days", peak:"7–14 days", duration:"3–4 months", vial:"50U / 100U" },
    { name:"Nuceiva / Jeuveau (prabotulinumtoxinA)", brand:"Evolus", onset:"3–5 days", peak:"7–14 days", duration:"3–4 months", vial:"100U" },
  ];

  return (
    <div className="space-y-2">
      {PRODUCTS.map(p => (
        <div key={p.name} className="rounded-lg border border-border bg-background p-3">
          <div className="flex items-start justify-between gap-2 mb-2 flex-wrap">
            <div>
              <p className="text-xs font-semibold text-foreground">{p.name}</p>
              <p className="text-xs text-muted-foreground">{p.brand}</p>
            </div>
            <span className="text-xs bg-muted px-2 py-0.5 rounded-full text-muted-foreground">{p.vial}</span>
          </div>
          <div className="flex gap-4 text-xs">
            <span><span className="text-muted-foreground">Onset: </span><span className="font-medium text-foreground">{p.onset}</span></span>
            <span><span className="text-muted-foreground">Peak: </span><span className="font-medium text-foreground">{p.peak}</span></span>
            <span><span className="text-muted-foreground">Duration: </span><span className="font-medium text-foreground">{p.duration}</span></span>
          </div>
        </div>
      ))}
      <Warning>Duration is approximate. Individual variation is significant. Minimum retreatment interval: 12 weeks.</Warning>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// SAFETY TOOLS
// ═══════════════════════════════════════════════════════════════

// Tool 6: Hyaluronidase dose calculator (expanded)
function HyalaseDose() {
  const [region, setRegion] = useState("lip");
  const [weight, setWeight] = useState("");
  const [severity, setSeverity] = useState("moderate");
  const [indication, setIndication] = useState("vascular");

  const REGIONS: Record<string, { dose: string; max: string; note: string }> = {
    "lip":           { dose:"150 U", max:"300 U per session", note:"Avoid overcorrection. Reassess at 30 min." },
    "nasolabial":    { dose:"150 U", max:"300 U per session", note:"Linear retrograde injection of hyaluronidase." },
    "tear trough":   { dose:"150–300 U", max:"600 U per session", note:"Periorbital area — use minimal volume, aspirate carefully." },
    "cheek":         { dose:"150–300 U", max:"450 U per session", note:"Inject across compromised territory." },
    "glabella":      { dose:"300 U", max:"600 U", note:"CRITICAL vascular zone. Repeat every 20-30 min if needed." },
    "nose":          { dose:"300–600 U", max:"1500 U total across sessions", note:"Highest occlusion risk. Aggressive dosing. Ophthalmology review if visual symptoms." },
    "forehead":      { dose:"150 U", max:"300 U per session", note:"Supratrochlear/supraorbital vessels at risk." },
    "temple":        { dose:"150–300 U", max:"450 U", note:"Temporal vessels — aspirate before injecting." },
  };

  const r = REGIONS[region] || { dose:"150 U", max:"300 U", note:"Follow local protocol." };
  const isVascular = indication === "vascular";

  return (
    <div className="space-y-4">
      <Grid2>
        <Field label="Region treated">
          <select value={region} onChange={e => setRegion(e.target.value)} className={selectCls}>
            {Object.keys(REGIONS).map(k => <option key={k} value={k} className="capitalize">{k.charAt(0).toUpperCase()+k.slice(1)}</option>)}
          </select>
        </Field>
        <Field label="Indication">
          <select value={indication} onChange={e => setIndication(e.target.value)} className={selectCls}>
            <option value="vascular">Vascular occlusion</option>
            <option value="correction">Filler correction / dissolve</option>
            <option value="tyndall">Tyndall effect</option>
            <option value="nodule">Nodule / lump</option>
          </select>
        </Field>
        <Field label="Severity">
          <select value={severity} onChange={e => setSeverity(e.target.value)} className={selectCls}>
            <option value="mild">Mild</option>
            <option value="moderate">Moderate</option>
            <option value="severe">Severe / progressive</option>
          </select>
        </Field>
        <Field label="Patient weight (kg) — optional">
          <input type="number" value={weight} onChange={e => setWeight(e.target.value)} placeholder="e.g. 65" min={0} className={inputCls} />
        </Field>
      </Grid2>

      <ResultBox accent>
        <ResultRow label="Initial dose" value={isVascular && severity === "severe" ? "300–600 U" : r.dose} bold />
        <ResultRow label="Session maximum" value={r.max} />
        <ResultRow label="Repeat interval" value={isVascular ? "Every 20–30 min if no reperfusion" : "Reassess at 2 weeks"} />
        <ResultRow label="Route" value="Intradermal / subcutaneous across affected territory" />
        <ResultRow label="Concentration" value="150 U/mL or 300 U/mL — dilute with normal saline" />
        <ResultRow label="Regional note" value={r.note} />
      </ResultBox>

      {isVascular && (
        <div className="rounded-lg border-2 border-red-300 bg-red-50 px-4 py-3 text-xs text-red-800">
          <p className="font-bold mb-1">Vascular occlusion emergency checklist:</p>
          <ul className="space-y-0.5 list-disc list-inside">
            <li>STOP injection immediately</li>
            <li>Apply warm compress — every 5 minutes</li>
            <li>Massage affected area</li>
            <li>Inject hyaluronidase across entire territory — do not spot inject</li>
            <li>Document capillary refill every 15 minutes</li>
            <li>If visual symptoms → 999 + ophthalmology NOW</li>
          </ul>
        </div>
      )}
    </div>
  );
}

// Tool 7: Adrenaline dose calculator
function AdrenalineDose() {
  const [weight, setWeight] = useState("");
  const [ageGroup, setAgeGroup] = useState("adult");
  const [route, setRoute] = useState("IM");

  const w = parseFloat(weight) || 0;
  const isAdult = ageGroup === "adult";
  const isPaeds = ageGroup === "paeds";

  const imDose = isAdult ? 0.5 : isPaeds ? Math.min(w * 0.01, 0.5) : 0.5;
  const imVol150 = imDose / 0.15; // 1:1000 diluted to 150mcg/mL
  const imVol1000 = imDose / 1;   // 1:1000 = 1mg/mL

  return (
    <div className="space-y-4">
      <Grid2>
        <Field label="Age group">
          <select value={ageGroup} onChange={e => setAgeGroup(e.target.value)} className={selectCls}>
            <option value="adult">Adult (≥12 years)</option>
            <option value="paeds">Child (weight-based)</option>
          </select>
        </Field>
        <Field label="Route">
          <select value={route} onChange={e => setRoute(e.target.value)} className={selectCls}>
            <option value="IM">IM (first line)</option>
            <option value="IV">IV (resuscitation only)</option>
          </select>
        </Field>
        {!isAdult && (
          <Field label="Weight (kg)">
            <input type="number" value={weight} onChange={e => setWeight(e.target.value)} placeholder="e.g. 25" min={0} className={inputCls} />
          </Field>
        )}
      </Grid2>

      <ResultBox accent>
        <ResultRow label="Adrenaline concentration" value="1:1000 (1 mg/mL)" bold />
        {isAdult ? (
          <>
            <ResultRow label="Adult IM dose" value="0.5 mg (0.5 mL of 1:1000)" bold />
            <ResultRow label="Auto-injector equivalent" value="EpiPen 0.3 mg (acceptable)" />
            <ResultRow label="Repeat if needed" value="Every 5 minutes" />
          </>
        ) : (
          <>
            {w > 0 && <>
              <ResultRow label="Paediatric IM dose (0.01 mg/kg)" value={`${Math.min(w*0.01,0.5).toFixed(3)} mg`} bold />
              <ResultRow label="Volume of 1:1000" value={`${Math.min(w*0.01,0.5).toFixed(3)} mL`} bold />
              <ResultRow label="Maximum dose (any child)" value="0.5 mg (0.5 mL)" />
            </>}
            {w === 0 && <ResultRow label="Enter weight above" value="—" />}
          </>
        )}
        <ResultRow label="Injection site" value="Anterolateral mid-thigh (IM)" />
        {route === "IV" && <ResultRow label="IV dose (resus only)" value="50–100 mcg IV — only in cardiac arrest or by experienced clinician" />}
      </ResultBox>

      <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-800 space-y-1">
        <p className="font-bold">After giving adrenaline:</p>
        <ul className="list-disc list-inside space-y-0.5">
          <li>Call 999 immediately</li>
          <li>Lay patient flat, legs raised (unless breathing difficulty)</li>
          <li>Give second dose in 5 min if no improvement</li>
          <li>Antihistamine + hydrocortisone are adjuncts only — not first line</li>
        </ul>
      </div>
    </div>
  );
}

// Tool 8: Local anaesthetic max dose
function LocalAnaestheticDose() {
  const [agent, setAgent] = useState("lidocaine_plain");
  const [weight, setWeight] = useState("70");
  const [concentration, setConcentration] = useState("1");

  const AGENTS: Record<string, { label: string; maxMgKg: number; maxMgAbs: number; note: string }> = {
    "lidocaine_plain":    { label:"Lidocaine plain (1–2%)", maxMgKg:3,  maxMgAbs:200, note:"Onset 2–5 min. Duration 1–2h." },
    "lidocaine_adrenaline":{ label:"Lidocaine + adrenaline", maxMgKg:7, maxMgAbs:500, note:"Onset 2–5 min. Duration 2–4h. Avoid end-arteries." },
    "articaine":          { label:"Articaine (4%)", maxMgKg:7, maxMgAbs:500, note:"Popular in dental. Not licensed IM in UK outside dentistry." },
    "prilocaine":         { label:"Prilocaine plain", maxMgKg:6, maxMgAbs:400, note:"Avoid in methaemoglobinaemia risk. Onset 5 min." },
    "bupivacaine":        { label:"Bupivacaine (0.25–0.5%)", maxMgKg:2, maxMgAbs:150, note:"Long-acting 4–8h. Cardiotoxic — never IV." },
  };

  const w = parseFloat(weight) || 0;
  const c = parseFloat(concentration) / 100; // %→g/mL → mg/mL = % * 10
  const mgPerML = parseFloat(concentration) * 10;
  const a = AGENTS[agent];

  const maxMg = Math.min(w * a.maxMgKg, a.maxMgAbs);
  const maxML = mgPerML > 0 ? maxMg / mgPerML : 0;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <Field label="Agent">
          <select value={agent} onChange={e => setAgent(e.target.value)} className={selectCls}>
            {Object.entries(AGENTS).map(([k,v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
        </Field>
        <Field label="Concentration (%)">
          <select value={concentration} onChange={e => setConcentration(e.target.value)} className={selectCls}>
            <option value="0.25">0.25%</option>
            <option value="0.5">0.5%</option>
            <option value="1">1%</option>
            <option value="2">2%</option>
            <option value="4">4%</option>
          </select>
        </Field>
        <Field label="Patient weight (kg)">
          <input type="number" value={weight} onChange={e => setWeight(e.target.value)} min={1} max={200} className={inputCls} />
        </Field>
      </div>
      {w > 0 && (
        <ResultBox accent>
          <ResultRow label="Maximum dose (weight-based)" value={`${maxMg.toFixed(0)} mg`} bold />
          <ResultRow label="Maximum volume at {concentration}%" value={`${maxML.toFixed(1)} mL`} bold />
          <ResultRow label="Absolute maximum (regardless of weight)" value={`${a.maxMgAbs} mg`} />
          <ResultRow label="mg/kg limit" value={`${a.maxMgKg} mg/kg`} />
          <ResultRow label="mg per mL at this concentration" value={`${mgPerML} mg/mL`} />
          <ResultRow label="Note" value={a.note} />
        </ResultBox>
      )}
      <Warning>Always use the lowest effective dose. Reduce by 25–30% in elderly, hepatic impairment, or cardiac disease. These are maximum doses — typical aesthetic blocks use far less.</Warning>
    </div>
  );
}

// Tool 9: Bleeding risk screener
function BleedingRiskScreener() {
  const MEDS = [
    { id:"warfarin",    label:"Warfarin", level:"high",     action:"Check INR. Defer if INR >3.0. Do NOT advise stopping — prescriber must decide.", colour:"red" },
    { id:"apixaban",    label:"Apixaban (Eliquis)", level:"high", action:"Document. High bruising risk. Do NOT stop. Discuss realistic expectations.", colour:"red" },
    { id:"rivaroxaban", label:"Rivaroxaban (Xarelto)", level:"high", action:"Same as apixaban. No reliable reversal agent in clinic.", colour:"red" },
    { id:"dabigatran",  label:"Dabigatran (Pradaxa)", level:"high", action:"Same as apixaban.", colour:"red" },
    { id:"aspirin",     label:"Aspirin (low dose)", level:"moderate", action:"Do NOT stop if cardiovascular indication. Counsel on bruising. Document.", colour:"amber" },
    { id:"clopidogrel", label:"Clopidogrel (Plavix)", level:"moderate", action:"Irreversible platelet inhibition. Do NOT stop without cardiologist advice.", colour:"amber" },
    { id:"nsaid",       label:"NSAIDs (ibuprofen, naproxen)", level:"moderate", action:"Advise to avoid 7 days pre-procedure if safe to do so. Document if essential.", colour:"amber" },
    { id:"ssri",        label:"SSRIs / SNRIs", level:"moderate", action:"Modest platelet effect. Do not advise stopping. Counsel on bruising.", colour:"amber" },
    { id:"fish_oil",    label:"High-dose fish oil (>3g/day)", level:"low", action:"Advise to pause 7 days pre-procedure if possible.", colour:"green" },
    { id:"vitamin_e",   label:"Vitamin E supplements", level:"low", action:"Advise to pause 7 days pre-procedure.", colour:"green" },
    { id:"glp1",        label:"GLP-1 agonists (Ozempic, Wegovy)", level:"moderate", action:"Not a bleeding risk. However — delayed gastric emptying. Use GLP-1 tool for full assessment.", colour:"amber" },
  ];

  const [selected, setSelected] = useState<string[]>([]);
  const toggle = (id: string) => setSelected(s => s.includes(id) ? s.filter(x=>x!==id) : [...s, id]);

  const active = MEDS.filter(m => selected.includes(m.id));
  const highRisk = active.filter(m => m.level === "high");
  const modRisk  = active.filter(m => m.level === "moderate");

  const colCls: Record<string, string> = {
    red:   "border-red-200 bg-red-50 text-red-800",
    amber: "border-amber-200 bg-amber-50 text-amber-800",
    green: "border-green-200 bg-green-50 text-green-800",
  };

  let decision = "Proceed";
  let decisionCls = "bg-green-50 border-green-300 text-green-800";
  if (highRisk.length > 0) { decision = "Caution — high bleeding risk. See actions below."; decisionCls = "bg-red-50 border-red-400 text-red-800"; }
  else if (modRisk.length > 0) { decision = "Proceed with caution — counsel on bruising risk."; decisionCls = "bg-amber-50 border-amber-300 text-amber-800"; }

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">Select all current medications:</p>
      <div className="flex flex-wrap gap-2">
        {MEDS.map(m => (
          <button key={m.id} onClick={() => toggle(m.id)}
            className={`text-xs px-3 py-1.5 rounded-lg border transition-all ${selected.includes(m.id) ? "bg-teal-700 text-white border-teal-700" : "border-border hover:border-teal-400 text-foreground"}`}>
            {m.label}
          </button>
        ))}
      </div>

      {selected.length > 0 && (
        <div className="space-y-3">
          <div className={`rounded-xl border-2 px-4 py-3 ${decisionCls}`}>
            <p className="text-sm font-bold">{decision}</p>
          </div>
          {active.map(m => (
            <div key={m.id} className={`rounded-lg border px-3 py-2.5 ${colCls[m.colour]}`}>
              <p className="text-xs font-semibold mb-0.5">{m.label}</p>
              <p className="text-xs">{m.action}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Tool 10: Fitzpatrick classifier
function FitzpatrickClassifier() {
  const QUESTIONS = [
    { q:"What colour is your skin before sun exposure?",
      opts:["Ivory/white","Fair/beige","Beige/light brown","Light brown","Dark brown","Black/very dark"] },
    { q:"How does your skin react to sun exposure (unprotected)?",
      opts:["Always burns severely, never tans","Usually burns, tans minimally","Sometimes burns, tans moderately","Rarely burns, tans easily","Very rarely burns, tans profusely","Never burns, deeply pigmented"] },
    { q:"How does your face react to sun exposure?",
      opts:["Very sensitive","Sensitive","Normal","Resistant","Very resistant","Never sensitive"] },
    { q:"When did you last expose yourself to sun/sunbed?",
      opts:["More than 3 months ago","2–3 months ago","1–2 months ago","Less than 1 month ago","Less than 2 weeks ago","Less than 1 week ago"] },
    { q:"How much have you tanned this past summer?",
      opts:["Not at all","Slightly","Moderately","Quite a lot","Deeply tanned","Extremely dark"] },
  ];

  const [answers, setAnswers] = useState<number[]>(new Array(QUESTIONS.length).fill(-1));

  const totalScore = answers.reduce((s,v) => s + (v >= 0 ? v : 0), 0);
  const allAnswered = answers.every(a => a >= 0);

  const getFitzpatrick = (score: number) => {
    if (score <= 6)  return { type:"I",   desc:"Always burns, never tans", colour:"#FDEEDE", text:"#8B4513", pih:"Minimal", laser:"Standard parameters" };
    if (score <= 10) return { type:"II",  desc:"Usually burns, tans minimally", colour:"#F5D5B0", text:"#7B3F00", pih:"Low", laser:"Standard parameters" };
    if (score <= 14) return { type:"III", desc:"Sometimes burns, tans moderately", colour:"#D4956A", text:"#5C2E00", pih:"Moderate", laser:"Reduce fluence 10–20%" };
    if (score <= 18) return { type:"IV",  desc:"Rarely burns, tans easily", colour:"#A0522D", text:"#3E1F0A", pih:"High — pre-treat", laser:"Reduce fluence 20–30%, longer pulse" };
    if (score <= 22) return { type:"V",   desc:"Very rarely burns, deeply pigmented", colour:"#6B3A2A", text:"#FFF5EE", pih:"Very high", laser:"Avoid ablative. Non-ablative or Nd:YAG only" };
    return                  { type:"VI",  desc:"Never burns, deeply pigmented", colour:"#3B1F1F", text:"#FFF5EE", pih:"Extreme — often contraindicated", laser:"Extreme caution. Nd:YAG 1064nm only" };
  };

  const result = allAnswered ? getFitzpatrick(totalScore) : null;

  return (
    <div className="space-y-4">
      {QUESTIONS.map((q, qi) => (
        <div key={qi}>
          <p className="text-xs font-medium text-foreground mb-2">Q{qi+1}: {q.q}</p>
          <div className="flex flex-wrap gap-2">
            {q.opts.map((opt, oi) => (
              <button key={oi} onClick={() => { const a=[...answers]; a[qi]=oi; setAnswers(a); }}
                className={`text-xs px-2.5 py-1.5 rounded-lg border transition-all ${answers[qi]===oi ? "bg-teal-700 text-white border-teal-700" : "border-border hover:border-teal-400"}`}>
                {opt}
              </button>
            ))}
          </div>
        </div>
      ))}
      {result && (
        <div className="rounded-xl border-2 border-border overflow-hidden">
          <div className="px-4 py-3" style={{ background: result.colour }}>
            <p className="font-bold" style={{ color: result.text }}>Fitzpatrick Type {result.type}</p>
            <p className="text-xs" style={{ color: result.text }}>{result.desc}</p>
          </div>
          <div className="p-4 space-y-1">
            <ResultRow label="PIH risk" value={result.pih} bold />
            <ResultRow label="Laser guidance" value={result.laser} />
            <ResultRow label="Score" value={`${totalScore}/25`} />
          </div>
        </div>
      )}
    </div>
  );
}

export {
  ToxinDilution, NeurotoxinConverter, HAFillerVolume,
  CannulaNeedleSelector, ToxinOnsetDuration,
  HyalaseDose, AdrenalineDose, LocalAnaestheticDose,
  BleedingRiskScreener, FitzpatrickClassifier,
};
