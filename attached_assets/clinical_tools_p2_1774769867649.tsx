/**
 * pages/clinical-tools-expanded.tsx (part 2)
 * ============================================
 * Tools 11-24 + main page component
 * Paste after the exports from part 1, or combine both parts into one file.
 */

import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/use-auth";
import {
  Syringe, Shield, Microscope, Users, LayoutDashboard,
  Loader2, AlertTriangle, CheckCircle, Copy, Plus, Trash2,
} from "lucide-react";
import {
  ToxinDilution, NeurotoxinConverter, HAFillerVolume,
  CannulaNeedleSelector, ToxinOnsetDuration,
  HyalaseDose, AdrenalineDose, LocalAnaestheticDose,
  BleedingRiskScreener, FitzpatrickClassifier,
} from "./clinical_tools_p1";

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
  return <div className={`rounded-xl p-4 border ${accent ? "bg-teal-50 border-teal-200" : "bg-muted/40 border-border"}`}>{children}</div>;
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
  return <div className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-800"><AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />{children}</div>;
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

function AILoader({ loading, error }: { loading: boolean; error: string | null }) {
  if (loading) return <div className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="w-3.5 h-3.5 animate-spin" />Running analysis…</div>;
  if (error) return <div className="flex gap-2 text-xs text-red-700 rounded-lg border border-red-200 bg-red-50 px-3 py-2"><AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />{error}</div>;
  return null;
}

// ═══════════════════════════════════════════════════════════════
// SKIN TOOLS
// ═══════════════════════════════════════════════════════════════

// Tool 11: Wrinkle severity grading scale (Lemperle-inspired)
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
  const sevColour = total < 5 ? "text-green-700" : total < 12 ? "text-amber-700" : "text-red-700";

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

// Tool 12: GAIS scale
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

// Tool 13: Facial ageing assessment
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

// Tool 14: Lip proportions / golden ratio
function LipProportions() {
  const [upperH, setUpperH] = useState("");
  const [lowerH, setLowerH] = useState("");
  const [lipW, setLipW] = useState("");
  const [philtrumH, setPhiltrumH] = useState("");

  const u = parseFloat(upperH)||0;
  const l = parseFloat(lowerH)||0;
  const w = parseFloat(lipW)||0;
  const p = parseFloat(philtrumH)||0;

  const idealRatio = 1/1.618; // upper:lower golden ratio ≈ 0.618
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

// Tool 15: AI Consent checklist
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

// Tool 16: AI Aftercare generator
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

// Tool 17: Photo capture guide (static)
function PhotoCaptureGuide() {
  const SHOTS = [
    { name:"Full face — frontal", desc:"Chin slightly down, eyes forward, neutral expression, mouth closed. Hair back.", bg:"#E1F5EE" },
    { name:"Right lateral (90°)", desc:"Turn head 90° right. Ear fully visible. Same neutral expression.", bg:"#E6F1FB" },
    { name:"Left lateral (90°)", desc:"Turn head 90° left. Ear fully visible.", bg:"#E6F1FB" },
    { name:"Right ¾ view (45°)", desc:"Turn head 45° right. Golden angle view.", bg:"#FAEEDA" },
    { name:"Left ¾ view (45°)", desc:"Turn head 45° left.", bg:"#FAEEDA" },
    { name:"Oblique (smile if relevant)", desc:"For lip/nasolabial: capture dynamic expression.", bg:"#FBEAF0" },
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

// Tool 18: AI GLP-1 assessment
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

// Tool 19: AI Vascular risk scorer
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
        <Field label="Injector experience">
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

// Tool 20: AI Toxin dosing guide
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

// Tool 21: Treatment pricing estimator
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

// Tool 22: CPD hours tracker
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
              <ResultRow key={cat} label={`${cat.charAt(0).toUpperCase()+cat.slice(1)}`} value={`${h.toFixed(1)} hrs`} />
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

// Tool 23: Treatment interval guide
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

// Tool 24: eGFR & drug adjustment note
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
    // Injectables
    { id:"tox-dilution",  name:"Toxin dilution",          description:"Units/mL from vial + saline volume",             cat:"injectables", component: () => <ToxinDilution /> },
    { id:"tox-convert",   name:"Unit converter",          description:"Convert between Botox, Dysport, Xeomin, Azzalure", cat:"injectables", component: () => <NeurotoxinConverter /> },
    { id:"tox-dosing",    name:"Dosing guide by region",  description:"Region-specific dose, technique, warnings",        cat:"injectables", ai:true, component: (p) => <ToxinDosingGuide token={p.token} /> },
    { id:"ha-volume",     name:"HA filler volume",        description:"Volume ranges by region and correction severity",   cat:"injectables", component: () => <HAFillerVolume /> },
    { id:"cannula",       name:"Cannula vs needle",       description:"Technique selector based on region and risk",       cat:"injectables", component: () => <CannulaNeedleSelector /> },
    { id:"tox-onset",     name:"Onset & duration",        description:"Onset, peak, duration by brand",                   cat:"injectables", component: () => <ToxinOnsetDuration /> },
    // Safety
    { id:"hyalase",       name:"Hyaluronidase dose",      description:"Region-specific doses + emergency protocol",        cat:"safety", component: () => <HyalaseDose /> },
    { id:"vasc-risk",     name:"Vascular risk scorer",    description:"AI-scored risk by region, technique, layer",        cat:"safety", ai:true, component: (p) => <VascularRiskTool token={p.token} /> },
    { id:"glp1",          name:"GLP-1 assessment",        description:"Aesthetic implications of GLP-1 medications",       cat:"safety", ai:true, component: (p) => <GLP1Tool token={p.token} /> },
    { id:"adrenaline",    name:"Adrenaline dose",         description:"Weight-based adrenaline for anaphylaxis",           cat:"safety", component: () => <AdrenalineDose /> },
    { id:"local-anaes",   name:"Local anaesthetic max",   description:"Maximum safe dose by agent, weight, concentration", cat:"safety", component: () => <LocalAnaestheticDose /> },
    { id:"bleed-risk",    name:"Bleeding risk screener",  description:"Anticoagulant / antiplatelet assessment",           cat:"safety", component: () => <BleedingRiskScreener /> },
    // Skin
    { id:"fitzpatrick",   name:"Fitzpatrick classifier",  description:"Skin type I–VI with treatment implications",        cat:"skin", component: () => <FitzpatrickClassifier /> },
    { id:"wrinkle",       name:"Wrinkle grading",         description:"Lemperle-based severity score by region",           cat:"skin", component: () => <WrinkleGrading /> },
    { id:"gais",          name:"GAIS outcome scale",      description:"Global aesthetic improvement — clinician + patient", cat:"skin", component: () => <GAISScale /> },
    { id:"ageing",        name:"Facial ageing assessment",description:"8-domain structured ageing profile",               cat:"skin", component: () => <FacialAgeingAssessment /> },
    // Patient
    { id:"lip-ratio",     name:"Lip proportions",        description:"Golden ratio assessment with augmentation guide",    cat:"patient", component: () => <LipProportions /> },
    { id:"consent",       name:"Consent checklist",      description:"AI-generated treatment-specific consent",            cat:"patient", ai:true, component: (p) => <ConsentChecklist token={p.token} /> },
    { id:"aftercare",     name:"Aftercare generator",    description:"AI-generated patient aftercare sheet",               cat:"patient", ai:true, component: (p) => <AftercareGenerator token={p.token} /> },
    { id:"photo-guide",   name:"Photo capture guide",    description:"Standardised documentation protocol",               cat:"patient", component: () => <PhotoCaptureGuide /> },
    // Clinic
    { id:"pricing",       name:"Pricing estimator",      description:"Break-even and retail price calculator",             cat:"clinic", component: () => <PricingEstimator /> },
    { id:"cpd",           name:"CPD tracker",            description:"Log and track CPD hours vs JCCP requirements",       cat:"clinic", component: () => <CPDTracker /> },
    { id:"interval",      name:"Treatment intervals",    description:"Minimum and recommended retreatment intervals",      cat:"clinic", component: () => <TreatmentIntervalGuide /> },
    { id:"egfr",          name:"eGFR & drug notes",      description:"CKD staging + aesthetic drug adjustments",          cat:"clinic", component: () => <EGFRNote /> },
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
