/**
 * pages/clinical-tools-expanded.tsx
 * All 24 clinical tools for aesthetic injectable medicine.
 * Route: /clinical-tools
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/use-auth";
import {
  Syringe, Shield, Microscope, Users, LayoutDashboard,
  ChevronDown, ChevronUp, Loader2, AlertTriangle,
  CheckCircle, Copy, Plus, Trash2,
} from "lucide-react";

const inputCls = "w-full text-sm rounded-lg border border-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-400 bg-background text-foreground";
const selectCls = inputCls;
const labelCls = "text-xs font-medium text-gray-500 block mb-1";

function Field({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return <div className={className}><label className={labelCls}>{label}</label>{children}</div>;
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
      <span className={`text-xs text-right max-w-[60%] ${bold ? "font-semibold text-foreground" : "text-foreground"}`}>{value}</span>
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
function AILoader({ loading, error }: { loading: boolean; error: string | null }) {
  if (loading) return <div className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="w-3.5 h-3.5 animate-spin" />Running analysis…</div>;
  if (error) return <div className="flex gap-2 text-xs text-red-700 rounded-lg border border-red-200 bg-red-50 px-3 py-2"><AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />{error}</div>;
  return null;
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

function ToxinDilution() {
  const [vial, setVial] = useState("100");
  const [saline, setSaline] = useState("2.5");
  const vialU = parseFloat(vial) || 0;
  const salineML = parseFloat(saline) || 0;
  const uPerML = salineML > 0 ? vialU / salineML : 0;
  const uPer01 = uPerML / 10;
  const uPerInsulin = uPerML / 100;
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

function NeurotoxinConverter() {
  const [from, setFrom] = useState("botox");
  const [units, setUnits] = useState("20");
  const RATIOS: Record<string, { label: string; toBotox: number }> = {
    botox:     { label: "Botox / Bocouture / Xeomin (1:1)", toBotox: 1 },
    azzalure:  { label: "Azzalure (Speywood)", toBotox: 1/2.5 },
    dysport:   { label: "Dysport (Galderma)", toBotox: 1/3 },
    letybo:    { label: "Letybo (1:1 Botox)", toBotox: 1 },
    bocouture: { label: "Bocouture (1:1 Botox)", toBotox: 1 },
    xeomin:    { label: "Xeomin (1:1 Botox)", toBotox: 1 },
  };
  const inputU = parseFloat(units) || 0;
  const inBotox = inputU * RATIOS[from].toBotox;
  const conversions = Object.entries(RATIOS).map(([key, r]) => ({ key, label: r.label, units: inBotox / r.toBotox }));
  return (
    <div className="space-y-4">
      <Grid2>
        <Field label="From brand">
          <select value={from} onChange={e => setFrom(e.target.value)} className={selectCls}>
            {Object.entries(RATIOS).map(([k, r]) => <option key={k} value={k}>{r.label}</option>)}
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
  let recommendation = "needle", rationale = "", colour = "amber";
  if (isCannulaZone || (highVascular && !isNeedleZone)) {
    recommendation = "cannula"; colour = "green";
    rationale = `${isCannulaZone ? "Region anatomy favours cannula. " : ""}${highVascular ? "High vascular risk area — cannula reduces intravascular injection risk. " : ""}Cannula preferred for this combination.`;
  } else if (isNeedleZone) {
    recommendation = "needle"; colour = "amber";
    rationale = "This region typically requires needle technique for precision. Extra care with aspiration and slow injection.";
  } else {
    recommendation = "either"; colour = "blue";
    rationale = "Either technique is appropriate. Consider cannula if vascular risk is a concern, needle for precision placement.";
  }
  if (lowExperience && recommendation !== "cannula") rationale += " Note: for novice injectors, cannula may reduce complication risk.";
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

function HyalaseDose() {
  const [region, setRegion] = useState("lip");
  const [weight, setWeight] = useState("");
  const [severity, setSeverity] = useState("moderate");
  const [indication, setIndication] = useState("vascular");
  const REGIONS: Record<string, { dose: string; max: string; note: string }> = {
    "lip":         { dose:"150 U", max:"300 U per session", note:"Avoid overcorrection. Reassess at 30 min." },
    "nasolabial":  { dose:"150 U", max:"300 U per session", note:"Linear retrograde injection of hyaluronidase." },
    "tear trough": { dose:"150–300 U", max:"600 U per session", note:"Periorbital area — use minimal volume, aspirate carefully." },
    "cheek":       { dose:"150–300 U", max:"450 U per session", note:"Inject across compromised territory." },
    "glabella":    { dose:"300 U", max:"600 U", note:"CRITICAL vascular zone. Repeat every 20-30 min if needed." },
    "nose":        { dose:"300–600 U", max:"1500 U total across sessions", note:"Highest occlusion risk. Aggressive dosing. Ophthalmology review if visual symptoms." },
    "forehead":    { dose:"150 U", max:"300 U per session", note:"Supratrochlear/supraorbital vessels at risk." },
    "temple":      { dose:"150–300 U", max:"450 U", note:"Temporal vessels — aspirate before injecting." },
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

function AdrenalineDose() {
  const [weight, setWeight] = useState("");
  const [ageGroup, setAgeGroup] = useState("adult");
  const [route, setRoute] = useState("IM");
  const w = parseFloat(weight) || 0;
  const isAdult = ageGroup === "adult";
  const isPaeds = ageGroup === "paeds";
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

function LocalAnaestheticDose() {
  const [agent, setAgent] = useState("lidocaine_plain");
  const [weight, setWeight] = useState("70");
  const [concentration, setConcentration] = useState("1");
  const AGENTS: Record<string, { label: string; maxMgKg: number; maxMgAbs: number; note: string }> = {
    "lidocaine_plain":     { label:"Lidocaine plain (1–2%)", maxMgKg:3,  maxMgAbs:200, note:"Onset 2–5 min. Duration 1–2h." },
    "lidocaine_adrenaline":{ label:"Lidocaine + adrenaline", maxMgKg:7,  maxMgAbs:500, note:"Onset 2–5 min. Duration 2–4h. Avoid end-arteries." },
    "articaine":           { label:"Articaine (4%)", maxMgKg:7,          maxMgAbs:500, note:"Popular in dental. Not licensed IM in UK outside dentistry." },
    "prilocaine":          { label:"Prilocaine plain", maxMgKg:6,        maxMgAbs:400, note:"Avoid in methaemoglobinaemia risk. Onset 5 min." },
    "bupivacaine":         { label:"Bupivacaine (0.25–0.5%)", maxMgKg:2, maxMgAbs:150, note:"Long-acting 4–8h. Cardiotoxic — never IV." },
  };
  const w = parseFloat(weight) || 0;
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
          <ResultRow label={`Maximum volume at ${concentration}%`} value={`${maxML.toFixed(1)} mL`} bold />
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

// ═══════════════════════════════════════════════════════════════
// SKIN TOOLS
// ═══════════════════════════════════════════════════════════════

function WrinkleGrading() {
  const REGIONS = [
    "Forehead lines","Glabellar lines","Periorbital (crow's feet)",
    "Nasolabial folds","Perioral lines","Marionette lines","Jowls","Neck"
  ];
  const GRADES = [0,1,2,3,4,5];
  const GRADE_DESC = ["None","Just visible","Shallow","Moderately deep","Deep","Very deep / redundant skin"];
  const [scores, setScores] = useState<Record<string,number>>({});
  const total = Object.values(scores).reduce((s,v)=>s+v,0);
  const rated = Object.keys(scores).length;
  const severity = total < 5 ? "Mild" : total < 12 ? "Moderate" : total < 20 ? "Significant" : "Severe";
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">Rate each region 0 (none) to 5 (very deep/redundant):</p>
      {REGIONS.map(r => (
        <div key={r} className="flex items-center gap-3">
          <span className="text-xs text-foreground w-44 flex-shrink-0">{r}</span>
          <div className="flex gap-1 flex-1">
            {GRADES.map(g => (
              <button key={g} onClick={() => setScores(s=>({...s,[r]:g}))}
                className={`w-8 h-8 rounded-md text-xs font-medium border transition-all ${scores[r]===g ? "bg-teal-700 text-white border-teal-700" : "border-border hover:border-teal-400 text-foreground"}`}>
                {g}
              </button>
            ))}
          </div>
          {scores[r] !== undefined && (
            <span className="text-xs text-muted-foreground w-24 text-right">{GRADE_DESC[scores[r]]}</span>
          )}
        </div>
      ))}
      {rated > 0 && (
        <ResultBox accent>
          <ResultRow label="Total score" value={`${total} / ${REGIONS.length * 5}`} bold />
          <ResultRow label="Overall severity" value={severity} bold />
          <ResultRow label="Regions rated" value={`${rated} / ${REGIONS.length}`} />
        </ResultBox>
      )}
      <Warning>Based on modified Lemperle scale. Use at every consultation for consistent documentation and before/after comparison.</Warning>
    </div>
  );
}

function GAISScale() {
  const [clinician, setClinician] = useState<number>(-1);
  const [patient, setPatient] = useState<number>(-1);
  const [notes, setNotes] = useState("");
  const SCORES = [
    { score:3, label:"Much improved", desc:"Marked improvement from baseline", colour:"bg-green-100 text-green-800 border-green-300" },
    { score:2, label:"Improved", desc:"Clear improvement from baseline", colour:"bg-green-50 text-green-700 border-green-200" },
    { score:1, label:"Slightly improved", desc:"Slight improvement from baseline", colour:"bg-teal-50 text-teal-700 border-teal-200" },
    { score:0, label:"No change", desc:"No change from baseline", colour:"bg-gray-50 text-gray-600 border-gray-200" },
    { score:-1, label:"Worse", desc:"Worse than baseline", colour:"bg-red-50 text-red-700 border-red-200" },
  ];
  return (
    <div className="space-y-4">
      <div>
        <p className="text-xs font-medium text-foreground mb-2">Clinician GAIS</p>
        <div className="flex flex-wrap gap-2">
          {SCORES.map(s => (
            <button key={s.score} onClick={() => setClinician(s.score)}
              className={`text-xs px-3 py-2 rounded-lg border transition-all ${clinician===s.score ? "bg-teal-700 text-white border-teal-700" : "border-border hover:border-teal-400"}`}>
              {s.label}
            </button>
          ))}
        </div>
      </div>
      <div>
        <p className="text-xs font-medium text-foreground mb-2">Patient GAIS</p>
        <div className="flex flex-wrap gap-2">
          {SCORES.map(s => (
            <button key={s.score} onClick={() => setPatient(s.score)}
              className={`text-xs px-3 py-2 rounded-lg border transition-all ${patient===s.score ? "bg-teal-700 text-white border-teal-700" : "border-border hover:border-teal-400"}`}>
              {s.label}
            </button>
          ))}
        </div>
      </div>
      <Field label="Notes">
        <textarea value={notes} onChange={e=>setNotes(e.target.value)} rows={2} placeholder="Optional clinical notes for record…" className={`${inputCls} resize-none`} />
      </Field>
      {(clinician>=0||patient>=0) && (
        <ResultBox accent>
          {clinician>=0 && <ResultRow label="Clinician GAIS" value={SCORES.find(s=>s.score===clinician)?.label||""} bold />}
          {patient>=0   && <ResultRow label="Patient GAIS"   value={SCORES.find(s=>s.score===patient)?.label||""} bold />}
          {clinician>=0 && patient>=0 && clinician!==patient && (
            <ResultRow label="Discordance" value="Clinician and patient scores differ — document discussion" />
          )}
        </ResultBox>
      )}
    </div>
  );
}

function FacialAgeingAssessment() {
  const DOMAINS = [
    { id:"volume", label:"Volume loss", desc:"Facial fat compartments, bony resorption" },
    { id:"skin",   label:"Skin quality", desc:"Texture, elasticity, fine lines" },
    { id:"ptosis", label:"Facial ptosis", desc:"Brow, midface, jowl, neck descent" },
    { id:"dynamic",label:"Dynamic lines", desc:"Expression lines visible in motion" },
    { id:"static", label:"Static lines", desc:"Lines at rest (NLF, marionette, glabella)" },
    { id:"pigment", label:"Pigmentation", desc:"Sunspots, melasma, uneven tone" },
    { id:"vascular",label:"Vascular changes", desc:"Redness, telangiectasia, rosacea" },
    { id:"neck",   label:"Neck / décolletage", desc:"Banding, crepiness, sun damage" },
  ];
  const [scores, setScores] = useState<Record<string,number>>({});
  const total = Object.values(scores).reduce((s,v)=>s+v,0);
  const maxTotal = DOMAINS.length * 3;
  const PRIORITY = DOMAINS
    .filter(d => scores[d.id] !== undefined && scores[d.id] >= 2)
    .sort((a,b) => (scores[b.id]||0) - (scores[a.id]||0))
    .map(d => d.label);
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">Rate each domain: 0 = none · 1 = mild · 2 = moderate · 3 = severe</p>
      {DOMAINS.map(d => (
        <div key={d.id} className="flex items-center gap-3">
          <div className="w-40 flex-shrink-0">
            <p className="text-xs font-medium text-foreground">{d.label}</p>
            <p className="text-xs text-muted-foreground">{d.desc}</p>
          </div>
          <div className="flex gap-2">
            {[0,1,2,3].map(g => (
              <button key={g} onClick={() => setScores(s=>({...s,[d.id]:g}))}
                className={`w-10 h-8 rounded-lg text-xs font-medium border transition-all ${scores[d.id]===g ? "bg-teal-700 text-white border-teal-700" : "border-border hover:border-teal-400 text-foreground"}`}>
                {g}
              </button>
            ))}
          </div>
        </div>
      ))}
      {Object.keys(scores).length > 0 && (
        <ResultBox accent>
          <ResultRow label="Total ageing score" value={`${total} / ${maxTotal}`} bold />
          {PRIORITY.length > 0 && <ResultRow label="Priority areas" value={PRIORITY.join(", ")} bold />}
        </ResultBox>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// PATIENT TOOLS
// ═══════════════════════════════════════════════════════════════

function LipProportions() {
  const [upperH, setUpperH] = useState("");
  const [lowerH, setLowerH] = useState("");
  const [lipW, setLipW] = useState("");
  const [philtrumH, setPhiltrumH] = useState("");
  const u = parseFloat(upperH)||0;
  const l = parseFloat(lowerH)||0;
  const w = parseFloat(lipW)||0;
  const p = parseFloat(philtrumH)||0;
  const idealRatio = 1/1.618;
  const actualRatio = l > 0 ? u/l : 0;
  const ratioIdeal = Math.abs(actualRatio - idealRatio) < 0.1;
  const widthHeightRatio = (u+l) > 0 ? w/(u+l) : 0;
  const whrIdeal = widthHeightRatio >= 3 && widthHeightRatio <= 4;
  const philtrumRatio = p > 0 && u > 0 ? p/u : 0;
  const philtrumIdeal = philtrumRatio >= 1 && philtrumRatio <= 1.5;
  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">Enter lip measurements in mm. All fields optional.</p>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Upper lip height (mm)">
          <input type="number" value={upperH} onChange={e=>setUpperH(e.target.value)} placeholder="e.g. 8" min={0} className={inputCls} />
        </Field>
        <Field label="Lower lip height (mm)">
          <input type="number" value={lowerH} onChange={e=>setLowerH(e.target.value)} placeholder="e.g. 13" min={0} className={inputCls} />
        </Field>
        <Field label="Lip width (mm)">
          <input type="number" value={lipW} onChange={e=>setLipW(e.target.value)} placeholder="e.g. 55" min={0} className={inputCls} />
        </Field>
        <Field label="Philtrum height (mm)">
          <input type="number" value={philtrumH} onChange={e=>setPhiltrumH(e.target.value)} placeholder="e.g. 12" min={0} className={inputCls} />
        </Field>
      </div>
      {(u>0||l>0||w>0) && (
        <ResultBox accent>
          {u>0&&l>0 && <>
            <ResultRow label="Upper:lower ratio" value={`${actualRatio.toFixed(2)} (ideal ≈ 0.62)`} bold />
            <ResultRow label="Ratio assessment" value={ratioIdeal ? "Within ideal range" : actualRatio < 0.5 ? "Upper lip relatively thin — augmentation may be appropriate" : "Upper lip relatively full — assess before augmenting"} />
          </>}
          {w>0&&(u+l>0) && <>
            <ResultRow label="Width:height ratio" value={`${widthHeightRatio.toFixed(1)} (ideal 3.0–4.0)`} />
            <ResultRow label="Width assessment" value={whrIdeal ? "Within ideal range" : "May benefit from width or volume adjustment"} />
          </>}
          {p>0&&u>0 && <>
            <ResultRow label="Philtrum:upper ratio" value={`${philtrumRatio.toFixed(2)} (ideal 1.0–1.5)`} />
            <ResultRow label="Philtrum assessment" value={philtrumIdeal ? "Ideal proportions" : p > u*1.5 ? "Long philtrum — toxin +/- filler may help" : "Short philtrum"} />
          </>}
        </ResultBox>
      )}
      <Warning>These are population-based aesthetic ideals. Individual ethnic variation is significant. Patient preference always takes precedence over mathematical ratios.</Warning>
    </div>
  );
}

function ConsentChecklist({ token }: { token: string }) {
  const [treatment, setTreatment] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string|null>(null);
  const [copied, setCopied] = useState(false);
  const run = async () => {
    if (!treatment.trim()) return;
    setLoading(true); setError(null); setResult(null);
    try {
      const data = await callTool("/api/tools/consent-checklist", { treatment, jurisdiction:"UK" }, token);
      setResult(data);
    } catch(e:any) { setError(e.message); }
    finally { setLoading(false); }
  };
  const copyText = () => {
    if (!result) return;
    const lines = [
      `Consent checklist: ${result.treatment}`,
      "\nCommon risks (>1%):", ...(result.risks_common||[]).map((r:string)=>`• ${r}`),
      "\nRare serious risks:", ...(result.risks_rare_serious||[]).map((r:string)=>`• ${r}`),
      "\nAlternatives:", ...(result.alternatives_discussed||[]).map((r:string)=>`• ${r}`),
      "\nDocumentation required:", ...(result.documentation_checklist||[]).map((r:string)=>`□ ${r}`),
    ];
    navigator.clipboard.writeText(lines.join("\n")).then(()=>{ setCopied(true); setTimeout(()=>setCopied(false),2000); });
  };
  return (
    <div className="space-y-4">
      <Field label="Treatment">
        <input type="text" value={treatment} onChange={e=>setTreatment(e.target.value)}
          placeholder="e.g. lip filler, toxin forehead, cheek augmentation"
          className={inputCls} onKeyDown={e=>e.key==="Enter"&&run()} />
      </Field>
      <Button onClick={run} disabled={loading||!treatment.trim()} className="w-full bg-teal-700 hover:bg-teal-800 text-white gap-2">
        {loading ? <><Loader2 className="w-4 h-4 animate-spin" />Generating…</> : "Generate consent checklist"}
      </Button>
      <AILoader loading={false} error={error} />
      {result && (
        <div className="space-y-3">
          <div className="flex justify-end">
            <Button variant="outline" size="sm" onClick={copyText} className="text-xs gap-1.5">
              {copied ? <><CheckCircle className="w-3.5 h-3.5" />Copied</> : <><Copy className="w-3.5 h-3.5" />Copy</>}
            </Button>
          </div>
          {[
            { title:"Common risks (>1%)", items:result.risks_common, colour:"amber" },
            { title:"Uncommon risks (0.1–1%)", items:result.risks_uncommon, colour:"amber" },
            { title:"Rare serious risks", items:result.risks_rare_serious, colour:"red" },
            { title:"Alternatives to document", items:result.alternatives_discussed, colour:"gray" },
            { title:"Post-care to discuss", items:result.post_care_summary, colour:"teal" },
            { title:"When to seek help", items:result.when_to_seek_help, colour:"red" },
            { title:"Documentation checklist", items:result.documentation_checklist, colour:"blue" },
          ].map(section => section.items?.length > 0 && (
            <div key={section.title}>
              <p className="text-xs font-semibold text-foreground mb-1">{section.title}</p>
              <ul className="space-y-0.5">
                {section.items.map((item: string, i: number) => (
                  <li key={i} className="text-xs text-muted-foreground flex gap-1.5"><span className="mt-1 w-1 h-1 rounded-full bg-muted-foreground flex-shrink-0" />{item}</li>
                ))}
              </ul>
            </div>
          ))}
          {result.jccp_note && <Warning>{result.jccp_note}</Warning>}
          {result.cooling_off_note && (
            <div className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800">{result.cooling_off_note}</div>
          )}
        </div>
      )}
    </div>
  );
}

function AftercareGenerator({ token }: { token: string }) {
  const [treatment, setTreatment] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string|null>(null);
  const run = async () => {
    if (!treatment.trim()) return;
    setLoading(true); setError(null); setResult(null);
    try {
      const data = await callTool("/api/tools/aftercare", { treatment }, token);
      setResult(data);
    } catch(e:any) { setError(e.message); }
    finally { setLoading(false); }
  };
  return (
    <div className="space-y-4">
      <Field label="Treatment">
        <input type="text" value={treatment} onChange={e=>setTreatment(e.target.value)}
          placeholder="e.g. lip filler, botox forehead" className={inputCls}
          onKeyDown={e=>e.key==="Enter"&&run()} />
      </Field>
      <Button onClick={run} disabled={loading||!treatment.trim()} className="w-full bg-teal-700 hover:bg-teal-800 text-white gap-2">
        {loading ? <><Loader2 className="w-4 h-4 animate-spin" />Generating…</> : "Generate aftercare sheet"}
      </Button>
      <AILoader loading={false} error={error} />
      {result && (
        <div className="space-y-3">
          {result.patient_note && (
            <div className="rounded-lg border border-teal-200 bg-teal-50 px-3 py-2.5 text-xs text-teal-800 font-medium">{result.patient_note}</div>
          )}
          {[
            { title:"What to expect", items:result.what_to_expect },
            { title:"First 24 hours", items:result.first_24_hours },
            { title:"First week", items:result.first_week },
            { title:"What to avoid", items:result.avoid },
            { title:"Call the clinic if", items:result.when_to_call_clinic },
            { title:"Go to A&E if", items:result.when_emergency },
          ].map(s => s.items?.length > 0 && (
            <div key={s.title}>
              <p className="text-xs font-semibold text-foreground mb-1">{s.title}</p>
              <ul className="space-y-0.5">
                {s.items.map((item:string,i:number) => (
                  <li key={i} className="text-xs text-muted-foreground flex gap-1.5"><span className="mt-1 w-1 h-1 rounded-full bg-muted-foreground flex-shrink-0" />{item}</li>
                ))}
              </ul>
            </div>
          ))}
          {result.follow_up && <ResultBox><ResultRow label="Follow up" value={result.follow_up} /></ResultBox>}
        </div>
      )}
    </div>
  );
}

function PhotoCaptureGuide() {
  const SHOTS = [
    { name:"Full face — frontal", desc:"Chin slightly down, eyes forward, neutral expression, mouth closed. Hair back." },
    { name:"Right lateral (90°)", desc:"Turn head 90° right. Ear fully visible. Same neutral expression." },
    { name:"Left lateral (90°)", desc:"Turn head 90° left. Ear fully visible." },
    { name:"Right ¾ view (45°)", desc:"Turn head 45° right. Golden angle view." },
    { name:"Left ¾ view (45°)", desc:"Turn head 45° left." },
    { name:"Oblique (smile if relevant)", desc:"For lip/nasolabial: capture dynamic expression." },
  ];
  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-teal-200 bg-teal-50 px-4 py-3 text-xs text-teal-800 space-y-1">
        <p className="font-semibold">Camera setup for all shots:</p>
        <ul className="list-disc list-inside space-y-0.5">
          <li>Camera at eye level</li>
          <li>Consistent diffuse lighting — no harsh shadows</li>
          <li>Plain background (white or grey)</li>
          <li>Same distance (approximately 50cm)</li>
          <li>Remove makeup where possible</li>
          <li>Hair tied back, ears visible</li>
        </ul>
      </div>
      {SHOTS.map((s,i) => (
        <div key={i} className="rounded-lg border border-border p-3 flex items-start gap-3">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold text-teal-700 bg-teal-100 flex-shrink-0">{i+1}</div>
          <div>
            <p className="text-xs font-semibold text-foreground">{s.name}</p>
            <p className="text-xs text-muted-foreground">{s.desc}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// CLINIC OPS TOOLS
// ═══════════════════════════════════════════════════════════════

function GLP1Tool({ token }: { token: string }) {
  const [drug, setDrug] = useState("semaglutide");
  const [months, setMonths] = useState("3");
  const [weightLoss, setWeightLoss] = useState("");
  const [treatment, setTreatment] = useState("");
  const [sedation, setSedation] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string|null>(null);
  const run = async () => {
    setLoading(true); setError(null); setResult(null);
    try {
      const data = await callTool("/api/tools/glp1-assessment", {
        drug_name: drug, duration_months: parseInt(months)||3,
        weight_loss_kg: parseFloat(weightLoss)||null,
        planned_treatment: treatment||"facial filler",
        sedation_planned: sedation,
      }, token);
      setResult(data);
    } catch(e:any) { setError(e.message); }
    finally { setLoading(false); }
  };
  const riskColour: Record<string,string> = {
    standard:"bg-green-50 border-green-300 text-green-800",
    caution:"bg-amber-50 border-amber-300 text-amber-800",
    high:"bg-red-50 border-red-400 text-red-800",
  };
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <Field label="GLP-1 medication">
          <select value={drug} onChange={e=>setDrug(e.target.value)} className={selectCls}>
            <option value="semaglutide">Semaglutide (Ozempic/Wegovy)</option>
            <option value="liraglutide">Liraglutide (Victoza/Saxenda)</option>
            <option value="tirzepatide">Tirzepatide (Mounjaro)</option>
            <option value="dulaglutide">Dulaglutide (Trulicity)</option>
          </select>
        </Field>
        <Field label="Duration on GLP-1 (months)">
          <input type="number" value={months} onChange={e=>setMonths(e.target.value)} min={0} className={inputCls} />
        </Field>
        <Field label="Weight lost (kg) — optional">
          <input type="number" value={weightLoss} onChange={e=>setWeightLoss(e.target.value)} placeholder="e.g. 12" min={0} className={inputCls} />
        </Field>
        <Field label="Planned treatment">
          <input type="text" value={treatment} onChange={e=>setTreatment(e.target.value)} placeholder="e.g. cheek filler, lip filler" className={inputCls} />
        </Field>
      </div>
      <div className="flex items-center gap-2">
        <button type="button" onClick={()=>setSedation(s=>!s)} className={`relative w-9 h-5 rounded-full transition-colors ${sedation?"bg-teal-600":"bg-gray-300"}`}>
          <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${sedation?"translate-x-4":"translate-x-0.5"}`} />
        </button>
        <span className="text-xs text-muted-foreground">Sedation or general anaesthesia planned</span>
      </div>
      <Button onClick={run} disabled={loading} className="w-full bg-teal-700 hover:bg-teal-800 text-white gap-2">
        {loading ? <><Loader2 className="w-4 h-4 animate-spin" />Assessing…</> : "Run GLP-1 impact assessment"}
      </Button>
      <AILoader loading={false} error={error} />
      {result && (
        <div className="space-y-3">
          <div className={`rounded-xl border-2 px-4 py-3 ${riskColour[result.risk_level]||riskColour.caution}`}>
            <p className="font-bold text-sm capitalize">{result.risk_level} consideration — {result.filler_recommendation} recommended</p>
            <p className="text-xs mt-1">{result.filler_rationale}</p>
          </div>
          {result.key_considerations?.map((k:string,i:number) => (
            <div key={i} className="text-xs flex gap-1.5 text-muted-foreground"><span className="mt-1 w-1 h-1 rounded-full bg-muted-foreground flex-shrink-0" />{k}</div>
          ))}
          {result.sedation_guidance && sedation && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-xs text-red-800"><span className="font-semibold">Sedation: </span>{result.sedation_guidance}</div>
          )}
          {result.timing_recommendation && (
            <ResultBox><ResultRow label="Treatment timing" value={result.timing_recommendation} /></ResultBox>
          )}
        </div>
      )}
    </div>
  );
}

function VascularRiskTool({ token }: { token: string }) {
  const [region, setRegion] = useState("");
  const [product, setProduct] = useState("HA");
  const [technique, setTechnique] = useState("needle");
  const [layer, setLayer] = useState("subcutaneous");
  const [experience, setExperience] = useState("intermediate");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string|null>(null);
  const run = async () => {
    if (!region.trim()) return;
    setLoading(true); setError(null); setResult(null);
    try {
      const data = await callTool("/api/tools/vascular-risk", {
        region, product, technique, layer,
        injector_level: experience, prior_treatment: false,
      }, token);
      setResult(data);
    } catch(e:any) { setError(e.message); }
    finally { setLoading(false); }
  };
  const riskCls: Record<string,string> = {
    low:"bg-green-50 border-green-300 text-green-800",
    moderate:"bg-amber-50 border-amber-300 text-amber-800",
    high:"bg-red-50 border-red-400 text-red-800",
    critical:"bg-red-100 border-red-600 text-red-900",
  };
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <Field label="Region">
          <input type="text" value={region} onChange={e=>setRegion(e.target.value)} placeholder="e.g. glabella, nose, lip" className={inputCls} />
        </Field>
        <Field label="Product">
          <select value={product} onChange={e=>setProduct(e.target.value)} className={selectCls}>
            <option value="HA">HA filler</option>
            <option value="CaHA">CaHA (Radiesse)</option>
            <option value="PLLA">PLLA (Sculptra)</option>
            <option value="toxin">Botulinum toxin</option>
          </select>
        </Field>
        <Field label="Technique">
          <select value={technique} onChange={e=>setTechnique(e.target.value)} className={selectCls}>
            <option value="needle">Needle</option>
            <option value="cannula">Cannula</option>
            <option value="bolus">Bolus injection</option>
            <option value="linear threading">Linear threading</option>
            <option value="fanning">Fanning</option>
          </select>
        </Field>
        <Field label="Injection layer">
          <select value={layer} onChange={e=>setLayer(e.target.value)} className={selectCls}>
            <option value="intradermal">Intradermal</option>
            <option value="subcutaneous">Subcutaneous</option>
            <option value="supraperiosteal">Supraperiosteal</option>
            <option value="intramuscular">Intramuscular</option>
          </select>
        </Field>
        <Field label="Injector experience" className="col-span-2">
          <select value={experience} onChange={e=>setExperience(e.target.value)} className={selectCls}>
            <option value="novice">Novice</option>
            <option value="intermediate">Intermediate</option>
            <option value="advanced">Advanced</option>
            <option value="expert">Expert</option>
          </select>
        </Field>
      </div>
      <Button onClick={run} disabled={loading||!region.trim()} className="w-full bg-teal-700 hover:bg-teal-800 text-white gap-2">
        {loading ? <><Loader2 className="w-4 h-4 animate-spin" />Scoring…</> : "Score vascular risk"}
      </Button>
      <AILoader loading={false} error={error} />
      {result && (
        <div className="space-y-3">
          <div className={`rounded-xl border-2 px-4 py-3 ${riskCls[result.risk_level]||riskCls.moderate}`}>
            <div className="flex items-center justify-between mb-1">
              <p className="font-bold text-sm">{result.risk_label}</p>
              <span className="text-lg font-bold">{result.risk_score}/100</span>
            </div>
            <div className="h-2 bg-white/60 rounded-full overflow-hidden">
              <div className={`h-full rounded-full ${result.risk_score>=70?"bg-red-500":result.risk_score>=40?"bg-amber-400":"bg-green-500"}`}
                style={{width:`${result.risk_score}%`}} />
            </div>
          </div>
          {result.named_vessels_at_risk?.length > 0 && (
            <ResultBox>
              <ResultRow label="Vessels at risk" value={result.named_vessels_at_risk.join(", ")} bold />
              <ResultRow label="Technique" value={`${result.technique_recommendation} preferred — ${result.technique_rationale}`} />
              <ResultRow label="Aspiration" value={result.aspiration_recommended ? `Recommended — ${result.aspiration_note}` : "Not required for this technique"} />
            </ResultBox>
          )}
          {result.mitigation_steps?.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-foreground mb-1">Mitigation steps:</p>
              {result.mitigation_steps.map((s:string,i:number) => (
                <div key={i} className="text-xs flex gap-1.5 text-muted-foreground py-0.5"><span className="mt-1 w-1 h-1 rounded-full bg-muted-foreground flex-shrink-0" />{s}</div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ToxinDosingGuide({ token }: { token: string }) {
  const [region, setRegion] = useState("");
  const [product, setProduct] = useState("Botox");
  const [patientType, setPatientType] = useState("average");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string|null>(null);
  const run = async () => {
    if (!region.trim()) return;
    setLoading(true); setError(null); setResult(null);
    try {
      const data = await callTool("/api/tools/toxin-dosing", { region, product, patient_type: patientType }, token);
      setResult(data);
    } catch(e:any) { setError(e.message); }
    finally { setLoading(false); }
  };
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <Field label="Region">
          <input type="text" value={region} onChange={e=>setRegion(e.target.value)}
            placeholder="e.g. glabella, forehead, crow's feet, masseter" className={inputCls} />
        </Field>
        <Field label="Product">
          <select value={product} onChange={e=>setProduct(e.target.value)} className={selectCls}>
            <option>Botox</option>
            <option>Dysport</option>
            <option>Xeomin</option>
            <option>Bocouture</option>
            <option>Azzalure</option>
            <option>Letybo</option>
          </select>
        </Field>
        <Field label="Patient type" className="col-span-2">
          <select value={patientType} onChange={e=>setPatientType(e.target.value)} className={selectCls}>
            <option value="average">Average adult</option>
            <option value="strong muscles">Strong muscles / male</option>
            <option value="first treatment">First treatment — conservative</option>
            <option value="fine lines">Fine lines / thin skin</option>
            <option value="elderly">Elderly / significant muscle atrophy</option>
          </select>
        </Field>
      </div>
      <Button onClick={run} disabled={loading||!region.trim()} className="w-full bg-teal-700 hover:bg-teal-800 text-white gap-2">
        {loading ? <><Loader2 className="w-4 h-4 animate-spin" />Looking up…</> : "Get dosing guidance"}
      </Button>
      <AILoader loading={false} error={error} />
      {result && (
        <div className="space-y-3">
          <ResultBox accent>
            <ResultRow label="Total dose range" value={result.total_dose_range_units} bold />
            <ResultRow label="Injection points" value={`${result.injection_points}`} />
            <ResultRow label="Dose per point" value={result.dose_per_point_units} />
            <ResultRow label="Dilution" value={result.recommended_dilution_ml} />
            <ResultRow label="Concentration" value={result.concentration_units_per_ml} />
            <ResultRow label="Depth" value={result.depth} />
            <ResultRow label="Onset" value={result.onset_days} />
            <ResultRow label="Peak" value={result.peak_days} />
            <ResultRow label="Duration" value={result.duration_months} />
            <ResultRow label="Patient type adjustment" value={result.patient_type_adjustment} />
          </ResultBox>
          {result.technique_notes?.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-foreground mb-1">Technique notes:</p>
              {result.technique_notes.map((n:string,i:number)=>(
                <div key={i} className="text-xs flex gap-1.5 text-muted-foreground py-0.5"><span className="mt-1 w-1 h-1 rounded-full bg-muted-foreground flex-shrink-0" />{n}</div>
              ))}
            </div>
          )}
          {result.warnings?.length>0 && <Warning>{result.warnings.join(" · ")}</Warning>}
          {result.manufacturer_approved===false && (
            <div className="text-xs rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-amber-800">
              This is an off-label use. Clinician responsibility — document informed consent.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PricingEstimator() {
  const [productCost, setProductCost] = useState("");
  const [consumables, setConsumables] = useState("15");
  const [timeMin, setTimeMin] = useState("30");
  const [hourlyRate, setHourlyRate] = useState("150");
  const [overhead, setOverhead] = useState("20");
  const pc = parseFloat(productCost)||0;
  const cons = parseFloat(consumables)||0;
  const time = parseFloat(timeMin)||0;
  const rate = parseFloat(hourlyRate)||0;
  const oh = parseFloat(overhead)||0;
  const labourCost = (time/60) * rate;
  const totalCost = pc + cons + labourCost;
  const totalWithOverhead = totalCost * (1 + oh/100);
  const retail1x5 = totalWithOverhead * 1.5;
  const retail2x = totalWithOverhead * 2;
  const retail2x5 = totalWithOverhead * 2.5;
  const fmt = (n:number) => `£${n.toFixed(0)}`;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <Field label="Product cost (£)"><input type="number" value={productCost} onChange={e=>setProductCost(e.target.value)} placeholder="e.g. 45" min={0} className={inputCls} /></Field>
        <Field label="Consumables (£)"><input type="number" value={consumables} onChange={e=>setConsumables(e.target.value)} placeholder="15" min={0} className={inputCls} /></Field>
        <Field label="Treatment time (minutes)"><input type="number" value={timeMin} onChange={e=>setTimeMin(e.target.value)} placeholder="30" min={0} className={inputCls} /></Field>
        <Field label="Your hourly rate (£/hr)"><input type="number" value={hourlyRate} onChange={e=>setHourlyRate(e.target.value)} placeholder="150" min={0} className={inputCls} /></Field>
        <Field label="Overhead % (rent, insurance, etc.)"><input type="number" value={overhead} onChange={e=>setOverhead(e.target.value)} placeholder="20" min={0} max={100} className={inputCls} /></Field>
      </div>
      {pc > 0 && (
        <ResultBox accent>
          <ResultRow label="Labour cost" value={fmt(labourCost)} />
          <ResultRow label="Total direct cost" value={fmt(totalCost)} />
          <ResultRow label="Total with overhead" value={fmt(totalWithOverhead)} bold />
          <ResultRow label="Retail at 1.5× (minimum viable)" value={fmt(retail1x5)} />
          <ResultRow label="Retail at 2× (standard)" value={fmt(retail2x)} bold />
          <ResultRow label="Retail at 2.5× (premium)" value={fmt(retail2x5)} />
          <ResultRow label="Break-even price" value={fmt(totalWithOverhead)} />
        </ResultBox>
      )}
      <Warning>These are estimates. Factor in consultation time, follow-up appointments, and patient acquisition costs. UK aesthetic pricing typically 1.8–3× direct costs.</Warning>
    </div>
  );
}

function CPDTracker() {
  const [entries, setEntries] = useState<{title:string;hours:number;category:string;date:string;provider:string}[]>([]);
  const [title, setTitle] = useState("");
  const [hours, setHours] = useState("");
  const [category, setCategory] = useState("clinical");
  const [date, setDate] = useState(new Date().toISOString().split("T")[0]);
  const [provider, setProvider] = useState("");
  const add = () => {
    if (!title.trim()||!hours) return;
    setEntries(e=>[...e,{title,hours:parseFloat(hours),category,date,provider}]);
    setTitle(""); setHours(""); setProvider("");
  };
  const totalHours = entries.reduce((s,e)=>s+e.hours,0);
  const byCategory = entries.reduce((acc,e)=>{ acc[e.category]=(acc[e.category]||0)+e.hours; return acc; },{} as Record<string,number>);
  const JCCP_MIN = 50;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <Field label="Activity title">
          <input type="text" value={title} onChange={e=>setTitle(e.target.value)} placeholder="e.g. Vascular anatomy masterclass" className={inputCls} />
        </Field>
        <Field label="Hours">
          <input type="number" value={hours} onChange={e=>setHours(e.target.value)} placeholder="e.g. 2.5" min={0} step={0.5} className={inputCls} />
        </Field>
        <Field label="Category">
          <select value={category} onChange={e=>setCategory(e.target.value)} className={selectCls}>
            <option value="clinical">Clinical</option>
            <option value="safety">Safety</option>
            <option value="ethics">Ethics / consent</option>
            <option value="management">Management</option>
            <option value="research">Research / audit</option>
          </select>
        </Field>
        <Field label="Date">
          <input type="date" value={date} onChange={e=>setDate(e.target.value)} className={inputCls} />
        </Field>
        <Field label="Provider (optional)">
          <input type="text" value={provider} onChange={e=>setProvider(e.target.value)} placeholder="e.g. JCCP, BCAM, BABTAC" className={inputCls} />
        </Field>
        <div className="flex items-end">
          <Button onClick={add} disabled={!title||!hours} className="w-full bg-teal-700 hover:bg-teal-800 text-white gap-1.5">
            <Plus className="w-4 h-4" /> Add entry
          </Button>
        </div>
      </div>
      {entries.length > 0 && (
        <div className="space-y-3">
          <ResultBox accent>
            <ResultRow label="Total CPD hours" value={`${totalHours.toFixed(1)} hrs`} bold />
            <ResultRow label="JCCP annual minimum" value={`${JCCP_MIN} hrs`} />
            <ResultRow label="Progress" value={`${Math.min(Math.round(totalHours/JCCP_MIN*100),100)}% complete`} />
            {Object.entries(byCategory).map(([cat,h]) => (
              <ResultRow key={cat} label={`${cat.charAt(0).toUpperCase()+cat.slice(1)}`} value={`${(h as number).toFixed(1)} hrs`} />
            ))}
          </ResultBox>
          <div className="space-y-1">
            {entries.map((e,i)=>(
              <div key={i} className="flex items-center gap-2 text-xs rounded-lg border border-border px-3 py-2">
                <span className="flex-1 text-foreground">{e.title}</span>
                <span className="text-muted-foreground">{e.date}</span>
                <span className="font-medium text-teal-700">{e.hours}h</span>
                <button onClick={()=>setEntries(en=>en.filter((_,j)=>j!==i))}>
                  <Trash2 className="w-3 h-3 text-muted-foreground hover:text-red-500" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function TreatmentIntervalGuide() {
  const INTERVALS = [
    { product:"Botox / Bocouture / Xeomin / Letybo", region:"Any",   min:"12 weeks", recommended:"16 weeks", note:"Allow full effects to dissipate. Antibody risk if re-treated too soon." },
    { product:"Dysport / Azzalure", region:"Any",                      min:"12 weeks", recommended:"16 weeks", note:"Same principle as above." },
    { product:"HA filler (Juvederm, Restylane)", region:"Lips",        min:"3 months",  recommended:"6 months", note:"Allow full integration. Top-up sooner if significant undercorrection." },
    { product:"HA filler", region:"Mid/lower face",                    min:"6 months",  recommended:"12 months", note:"Assess for accumulation before retreating." },
    { product:"HA filler", region:"Tear trough",                       min:"9 months",  recommended:"12+ months", note:"Very long retention in periorbital fat." },
    { product:"CaHA (Radiesse)", region:"Any",                         min:"12 months", recommended:"18 months", note:"Long-lasting biostimulator. Assess residual effect." },
    { product:"PLLA (Sculptra)", region:"Any",                         min:"4 weeks between sessions", recommended:"3 sessions over 12 weeks", note:"Collagen stimulator — results develop over months." },
    { product:"PRF / PRP", region:"Any",                               min:"4 weeks",   recommended:"4–6 weeks", note:"Series of 3–4 treatments typical." },
    { product:"Profhilo", region:"Any",                                min:"4 weeks",   recommended:"4–6 weeks", note:"Standard protocol: 2 sessions 4 weeks apart, then review." },
    { product:"Polynucleotides (PDRN)", region:"Any",                  min:"2 weeks",   recommended:"4 weeks", note:"Series typical. Follow manufacturer protocol." },
  ];
  return (
    <div className="space-y-2">
      {INTERVALS.map((r,i) => (
        <div key={i} className="rounded-lg border border-border p-3">
          <div className="flex items-start justify-between gap-2 mb-1.5 flex-wrap">
            <div>
              <p className="text-xs font-semibold text-foreground">{r.product}</p>
              <p className="text-xs text-muted-foreground">Region: {r.region}</p>
            </div>
          </div>
          <div className="flex gap-4 text-xs flex-wrap">
            <span><span className="text-muted-foreground">Minimum: </span><span className="font-medium text-red-700">{r.min}</span></span>
            <span><span className="text-muted-foreground">Recommended: </span><span className="font-medium text-teal-700">{r.recommended}</span></span>
          </div>
          {r.note && <p className="text-xs text-muted-foreground mt-1">{r.note}</p>}
        </div>
      ))}
      <Warning>Intervals are guidance only. Clinical assessment of residual product and patient response always takes precedence.</Warning>
    </div>
  );
}

function EGFRNote() {
  const [egfr, setEgfr] = useState("");
  const val = parseFloat(egfr)||0;
  const stage = val >= 90 ? {s:"G1",label:"Normal or high",colour:"green"} :
                val >= 60 ? {s:"G2",label:"Mildly reduced",colour:"green"} :
                val >= 45 ? {s:"G3a",label:"Mildly–moderately reduced",colour:"amber"} :
                val >= 30 ? {s:"G3b",label:"Moderately–severely reduced",colour:"amber"} :
                val >= 15 ? {s:"G4",label:"Severely reduced",colour:"red"} :
                            {s:"G5",label:"Kidney failure",colour:"red"};
  const DRUGS = [
    { drug:"Aciclovir / valaciclovir (pre-procedure antiviral prophylaxis)", note:val<30 ? "Dose reduction required — consult prescribing clinician" : "Standard dose appropriate" },
    { drug:"NSAIDs (post-procedure analgesia)", note:val<30 ? "Avoid NSAIDs — risk of acute kidney injury" : val<60 ? "Use with caution, short course only" : "Standard dose" },
    { drug:"Lidocaine (local anaesthetic)", note:"Renal impairment does not significantly affect lidocaine — standard max dose applies" },
    { drug:"Topical anaesthetic cream (EMLA/Ametop)", note:"Minimal systemic absorption — no dose adjustment required" },
  ];
  const colCls: Record<string,string> = { green:"bg-green-50 border-green-300 text-green-800", amber:"bg-amber-50 border-amber-300 text-amber-800", red:"bg-red-50 border-red-400 text-red-800" };
  return (
    <div className="space-y-4">
      <Field label="eGFR (mL/min/1.73m²)">
        <input type="number" value={egfr} onChange={e=>setEgfr(e.target.value)} placeholder="e.g. 65" min={0} max={200} className={inputCls} />
      </Field>
      {val > 0 && (
        <div className="space-y-3">
          <div className={`rounded-xl border-2 px-4 py-3 ${colCls[stage.colour]}`}>
            <p className="font-bold text-sm">CKD Stage {stage.s}</p>
            <p className="text-xs">{stage.label} — eGFR {val} mL/min/1.73m²</p>
          </div>
          <div>
            <p className="text-xs font-semibold text-foreground mb-2">Aesthetic drug considerations:</p>
            {DRUGS.map((d,i) => (
              <div key={i} className="border-b border-border py-2 last:border-0">
                <p className="text-xs font-medium text-foreground">{d.drug}</p>
                <p className="text-xs text-muted-foreground">{d.note}</p>
              </div>
            ))}
          </div>
        </div>
      )}
      <Warning>This is a reference tool. Always check current prescribing information and consult the prescribing clinician for patients with significant renal impairment.</Warning>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// MAIN PAGE
// ═══════════════════════════════════════════════════════════════

interface ToolDef {
  id: string;
  name: string;
  description: string;
  cat: string;
  ai?: boolean;
  component: (props: any) => JSX.Element;
}

export default function ClinicalToolsExpandedPage() {
  const { token } = useAuth();
  const [activeTab, setActiveTab] = useState("injectables");
  const [openTool, setOpenTool] = useState<string | null>(null);

  const TOOLS: ToolDef[] = [
    { id:"tox-dilution",  name:"Toxin dilution",          description:"Units/mL from vial + saline volume",              cat:"injectables", component: () => <ToxinDilution /> },
    { id:"tox-convert",   name:"Unit converter",          description:"Convert between Botox, Dysport, Xeomin, Azzalure", cat:"injectables", component: () => <NeurotoxinConverter /> },
    { id:"tox-dosing",    name:"Dosing guide by region",  description:"Region-specific dose, technique, warnings",        cat:"injectables", ai:true, component: (p) => <ToxinDosingGuide token={p.token} /> },
    { id:"ha-volume",     name:"HA filler volume",        description:"Volume ranges by region and correction severity",   cat:"injectables", component: () => <HAFillerVolume /> },
    { id:"cannula",       name:"Cannula vs needle",       description:"Technique selector based on region and risk",       cat:"injectables", component: () => <CannulaNeedleSelector /> },
    { id:"tox-onset",     name:"Onset & duration",        description:"Onset, peak, duration by brand",                   cat:"injectables", component: () => <ToxinOnsetDuration /> },
    { id:"hyalase",       name:"Hyaluronidase dose",      description:"Region-specific doses + emergency protocol",        cat:"safety", component: () => <HyalaseDose /> },
    { id:"vasc-risk",     name:"Vascular risk scorer",    description:"AI-scored risk by region, technique, layer",        cat:"safety", ai:true, component: (p) => <VascularRiskTool token={p.token} /> },
    { id:"glp1",          name:"GLP-1 assessment",        description:"Aesthetic implications of GLP-1 medications",       cat:"safety", ai:true, component: (p) => <GLP1Tool token={p.token} /> },
    { id:"adrenaline",    name:"Adrenaline dose",         description:"Weight-based adrenaline for anaphylaxis",           cat:"safety", component: () => <AdrenalineDose /> },
    { id:"local-anaes",   name:"Local anaesthetic max",   description:"Maximum safe dose by agent, weight, concentration", cat:"safety", component: () => <LocalAnaestheticDose /> },
    { id:"bleed-risk",    name:"Bleeding risk screener",  description:"Anticoagulant / antiplatelet assessment",           cat:"safety", component: () => <BleedingRiskScreener /> },
    { id:"fitzpatrick",   name:"Fitzpatrick classifier",  description:"Skin type I–VI with treatment implications",        cat:"skin", component: () => <FitzpatrickClassifier /> },
    { id:"wrinkle",       name:"Wrinkle grading",         description:"Lemperle-based severity score by region",           cat:"skin", component: () => <WrinkleGrading /> },
    { id:"gais",          name:"GAIS outcome scale",      description:"Global aesthetic improvement — clinician + patient", cat:"skin", component: () => <GAISScale /> },
    { id:"ageing",        name:"Facial ageing assessment",description:"8-domain structured ageing profile",                cat:"skin", component: () => <FacialAgeingAssessment /> },
    { id:"lip-ratio",     name:"Lip proportions",         description:"Golden ratio assessment with augmentation guide",   cat:"patient", component: () => <LipProportions /> },
    { id:"consent",       name:"Consent checklist",       description:"AI-generated treatment-specific consent",           cat:"patient", ai:true, component: (p) => <ConsentChecklist token={p.token} /> },
    { id:"aftercare",     name:"Aftercare generator",     description:"AI-generated patient aftercare sheet",              cat:"patient", ai:true, component: (p) => <AftercareGenerator token={p.token} /> },
    { id:"photo-guide",   name:"Photo capture guide",     description:"Standardised documentation protocol",              cat:"patient", component: () => <PhotoCaptureGuide /> },
    { id:"pricing",       name:"Pricing estimator",       description:"Break-even and retail price calculator",            cat:"clinic", component: () => <PricingEstimator /> },
    { id:"cpd",           name:"CPD tracker",             description:"Log and track CPD hours vs JCCP requirements",      cat:"clinic", component: () => <CPDTracker /> },
    { id:"interval",      name:"Treatment intervals",     description:"Minimum and recommended retreatment intervals",     cat:"clinic", component: () => <TreatmentIntervalGuide /> },
    { id:"egfr",          name:"eGFR & drug notes",       description:"CKD staging + aesthetic drug adjustments",         cat:"clinic", component: () => <EGFRNote /> },
  ];

  const TABS = [
    { id:"injectables", label:"Injectables", icon:<Syringe className="w-3.5 h-3.5" /> },
    { id:"safety",      label:"Safety",      icon:<Shield className="w-3.5 h-3.5" /> },
    { id:"skin",        label:"Skin",        icon:<Microscope className="w-3.5 h-3.5" /> },
    { id:"patient",     label:"Patient",     icon:<Users className="w-3.5 h-3.5" /> },
    { id:"clinic",      label:"Clinic ops",  icon:<LayoutDashboard className="w-3.5 h-3.5" /> },
  ];

  const visible = TOOLS.filter(t => t.cat === activeTab);

  return (
    <div className="max-w-2xl mx-auto px-4 py-6">
      <div className="mb-5">
        <h1 className="text-lg font-bold text-foreground mb-1">Clinical tools</h1>
        <p className="text-xs text-muted-foreground">24 evidence-based calculators and reference tools for aesthetic injectable medicine.</p>
      </div>

      <div className="flex gap-1 bg-muted rounded-lg p-1 mb-5 overflow-x-auto">
        {TABS.map(t => (
          <button key={t.id} onClick={() => { setActiveTab(t.id); setOpenTool(null); }}
            className={`flex-shrink-0 flex items-center gap-1.5 text-xs font-medium py-2 px-3 rounded-md transition-all ${activeTab===t.id ? "bg-background text-teal-700 shadow-sm" : "text-muted-foreground hover:text-foreground"}`}>
            {t.icon}{t.label}
          </button>
        ))}
      </div>

      <div className="space-y-2">
        {visible.map(tool => {
          const isOpen = openTool === tool.id;
          return (
            <div key={tool.id} className={`rounded-xl border transition-all ${isOpen ? "border-teal-300 shadow-sm" : "border-border"} bg-background overflow-hidden`}>
              <button className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left"
                onClick={() => setOpenTool(isOpen ? null : tool.id)}>
                <div className="flex items-center gap-2.5 min-w-0">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-semibold text-foreground">{tool.name}</p>
                      {tool.ai && <span className="text-xs bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded-full font-medium">AI</span>}
                    </div>
                    <p className="text-xs text-muted-foreground">{tool.description}</p>
                  </div>
                </div>
                {isOpen ? <ChevronUp className="w-4 h-4 text-muted-foreground flex-shrink-0" /> : <ChevronDown className="w-4 h-4 text-muted-foreground flex-shrink-0" />}
              </button>
              {isOpen && (
                <div className="border-t border-border px-4 pb-4 pt-4">
                  <tool.component token={token} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
