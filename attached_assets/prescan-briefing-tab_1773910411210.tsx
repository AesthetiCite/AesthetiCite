/**
 * PRE-PROCEDURE SAFETY PAGE — Pre-Scan Briefing Tab Addition
 * ===========================================================
 * This adds a third tab "Pre-Scan Briefing" to pre-procedure-safety.tsx
 *
 * HOW TO INTEGRATE:
 * 1. In your existing pre-procedure-safety.tsx, find the tab buttons block
 *    and add the third tab button (shown below)
 * 2. Add the PRESCAN state variables
 * 3. Add the tab 3 content block after the existing differential tab block
 * 4. The tab uses the existing activeTab state — extend it to include "prescan"
 *
 * The component is self-contained. No new dependencies beyond what's already imported.
 */

// ─────────────────────────────────────────────────────────────────────────────
// STEP 1: Update activeTab type
// Change: const [activeTab, setActiveTab] = useState<"check" | "differential">("check");
// To:
// const [activeTab, setActiveTab] = useState<"check" | "differential" | "prescan">("check");
// ─────────────────────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────────────────
// STEP 2: Add Pre-Scan state variables (paste after existing form state)
// ─────────────────────────────────────────────────────────────────────────────

const PRESCAN_STATE_ADDITIONS = `
  // Pre-Scan Briefing state
  const [prescanRegion, setPrescanRegion] = useState("");
  const [prescanExperience, setPrescanExperience] = useState("");
  const [prescanResult, setPrescanResult] = useState<PreScanBriefingResponse | null>(null);
  const [prescanLoading, setPrescanLoading] = useState(false);
  const [prescanError, setPrescanError] = useState("");

  async function handleRunPrescan() {
    if (!prescanRegion) { setPrescanError("Select a region first."); return; }
    setPrescanLoading(true); setPrescanError(""); setPrescanResult(null);
    try {
      const res = await fetch("/api/complications/prescan-briefing", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          region: prescanRegion,
          injector_experience_level: prescanExperience || undefined,
          has_ultrasound: true,
        }),
      });
      if (!res.ok) throw new Error("Briefing failed");
      const data = await res.json();
      setPrescanResult(data);
    } catch (e: any) {
      setPrescanError(e.message || "Failed to load briefing");
    } finally {
      setPrescanLoading(false);
    }
  }
`;

// ─────────────────────────────────────────────────────────────────────────────
// STEP 3: Add this type definition alongside your other types
// ─────────────────────────────────────────────────────────────────────────────

const PRESCAN_TYPE = `
interface PreScanBriefingResponse {
  request_id: string;
  generated_at_utc: string;
  region_label: string;
  risk_level: string;
  structures_to_identify: string[];
  doppler_settings: string;
  key_findings_to_document: string[];
  safe_windows: string[];
  abort_criteria: string[];
  evidence_note: string;
  disclaimer: string;
  junior_note?: string;
}
`;

// ─────────────────────────────────────────────────────────────────────────────
// STEP 4: Update the tabs header — add third tab button
// Find:
//   <button onClick={() => setActiveTab("differential")} ...>
//     <Microscope ... /> Complication Differential
//   </button>
// Add AFTER it:
// ─────────────────────────────────────────────────────────────────────────────

const THIRD_TAB_BUTTON = `
<button
  onClick={() => setActiveTab("prescan")}
  className={\`px-3 py-1.5 rounded-md text-xs font-semibold transition-all flex items-center gap-1.5 \${activeTab === "prescan" ? "bg-white text-slate-800 shadow-sm" : "text-slate-500 hover:text-slate-700"}\`}
>
  <Waves className="w-3 h-3" />
  Pre-Scan Briefing
</button>
`;

// ─────────────────────────────────────────────────────────────────────────────
// STEP 5: Add the full Pre-Scan Briefing tab content
// Paste this block AFTER the closing of the differential tab block
// (after the last </div> of {activeTab === "differential" && (...)})
// ─────────────────────────────────────────────────────────────────────────────

export function PreScanBriefingTab({
  prescanRegion, setPrescanRegion,
  prescanExperience, setPrescanExperience,
  prescanResult, prescanLoading, prescanError,
  handleRunPrescan
}: {
  prescanRegion: string;
  setPrescanRegion: (v: string) => void;
  prescanExperience: string;
  setPrescanExperience: (v: string) => void;
  prescanResult: any;
  prescanLoading: boolean;
  prescanError: string;
  handleRunPrescan: () => void;
}) {
  const riskColors: Record<string, string> = {
    very_high: "text-red-700 bg-red-50 border-red-200",
    high: "text-red-600 bg-red-50 border-red-100",
    moderate: "text-amber-700 bg-amber-50 border-amber-200",
    low: "text-emerald-700 bg-emerald-50 border-emerald-200",
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 grid grid-cols-1 lg:grid-cols-5 gap-6">

      {/* Form */}
      <div className="lg:col-span-2 space-y-4">
        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-1">
            {/* Waves icon */}
            <svg className="w-4 h-4 text-sky-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M3 7c3-2 6-2 9 0s6 2 9 0M3 12c3-2 6-2 9 0s6 2 9 0M3 17c3-2 6-2 9 0s6 2 9 0" />
            </svg>
            <h2 className="text-sm font-bold text-slate-800">Pre-Scan Briefing</h2>
          </div>
          <p className="text-xs text-slate-500 mb-4 leading-relaxed">
            Before using your ultrasound, AesthetiCite tells you exactly which structures
            to identify, safe injection windows, and abort criteria for the selected region.
            Based on RSNA 2025 and J Cosm Dermatology 2025 protocols.
          </p>

          <div className="space-y-3">
            {/* Region */}
            <div>
              <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
                Injection Region *
              </label>
              <select
                value={prescanRegion}
                onChange={e => setPrescanRegion(e.target.value)}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-400 transition-all"
              >
                <option value="">Select region</option>
                <option value="nose">Nose / Nasal Dorsum</option>
                <option value="temple">Temple / Temporal Hollow</option>
                <option value="forehead">Forehead / Frontal</option>
                <option value="tear trough">Tear Trough / Periorbital</option>
                <option value="glabella">Glabella / Frown Lines</option>
                <option value="nasolabial fold">Nasolabial Fold</option>
                <option value="lip">Lip / Perioral</option>
                <option value="jawline">Jawline / Chin</option>
                <option value="cheek">Cheek / Malar</option>
              </select>
            </div>

            {/* Experience */}
            <div>
              <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
                Injector Experience
              </label>
              <select
                value={prescanExperience}
                onChange={e => setPrescanExperience(e.target.value)}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-400 transition-all"
              >
                <option value="">Select level</option>
                <option value="junior">Junior (&lt; 2 years)</option>
                <option value="intermediate">Intermediate (2–5 years)</option>
                <option value="senior">Senior (5+ years)</option>
              </select>
            </div>
          </div>
        </div>

        {prescanError && (
          <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            {prescanError}
          </p>
        )}

        <button
          onClick={handleRunPrescan}
          disabled={prescanLoading}
          className="w-full bg-sky-700 hover:bg-sky-600 disabled:opacity-50 text-white font-semibold rounded-xl py-3 text-sm transition-colors flex items-center justify-center gap-2"
        >
          {prescanLoading ? (
            <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Generating briefing…</>
          ) : (
            <>
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M3 7c3-2 6-2 9 0s6 2 9 0M3 12c3-2 6-2 9 0s6 2 9 0M3 17c3-2 6-2 9 0s6 2 9 0" />
              </svg>
              Generate Pre-Scan Briefing
            </>
          )}
        </button>
      </div>

      {/* Results */}
      <div className="lg:col-span-3 space-y-4">

        {!prescanResult && !prescanLoading && (
          <div className="bg-white rounded-2xl border border-dashed border-slate-200 p-12 flex flex-col items-center text-center gap-3">
            <div className="w-12 h-12 rounded-full bg-sky-50 flex items-center justify-center">
              <svg className="w-6 h-6 text-sky-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M3 7c3-2 6-2 9 0s6 2 9 0M3 12c3-2 6-2 9 0s6 2 9 0M3 17c3-2 6-2 9 0s6 2 9 0" />
              </svg>
            </div>
            <p className="text-sm font-medium text-slate-500">Select a region to generate your pre-scan checklist</p>
            <p className="text-xs text-slate-400 max-w-xs">
              AesthetiCite will tell you which structures to identify before injection,
              Doppler settings, safe injection windows, and abort criteria.
            </p>
          </div>
        )}

        {prescanLoading && (
          <div className="bg-white rounded-2xl border border-slate-200 p-12 flex flex-col items-center gap-4">
            <div className="w-10 h-10 border-2 border-sky-200 border-t-sky-600 rounded-full animate-spin" />
            <p className="text-sm text-slate-500">Generating ultrasound briefing…</p>
          </div>
        )}

        {prescanResult && (
          <>
            {/* Header */}
            <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-base font-black text-slate-800">{prescanResult.region_label}</h3>
                  <p className="text-xs text-slate-500 mt-0.5">Pre-scan ultrasound briefing</p>
                </div>
                <span className={`text-xs font-bold border rounded-lg px-3 py-1.5 ${riskColors[prescanResult.risk_level] || riskColors.moderate}`}>
                  {prescanResult.risk_level.replace("_", " ").toUpperCase()} RISK
                </span>
              </div>
              {/* Doppler settings */}
              <div className="mt-3 bg-sky-50 border border-sky-200 rounded-xl px-3 py-2.5">
                <p className="text-[10px] font-bold text-sky-600 uppercase tracking-wider mb-1">Doppler Settings</p>
                <p className="text-xs text-sky-800">{prescanResult.doppler_settings}</p>
              </div>
            </div>

            {/* Structures to identify */}
            <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm">
              <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">
                Structures to Identify
              </h4>
              <ul className="space-y-2">
                {prescanResult.structures_to_identify.map((s: string, i: number) => (
                  <li key={i} className="flex items-start gap-2.5 text-xs text-slate-700">
                    <span className="flex-shrink-0 w-5 h-5 rounded-full bg-slate-100 text-slate-500 font-bold flex items-center justify-center text-[10px]">
                      {i + 1}
                    </span>
                    {s}
                  </li>
                ))}
              </ul>
            </div>

            {/* Key findings + Safe windows — 2 col */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm">
                <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">
                  Document These Findings
                </h4>
                <ul className="space-y-1.5">
                  {prescanResult.key_findings_to_document.map((f: string, i: number) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-slate-600">
                      <span className="text-slate-400 flex-shrink-0">›</span>{f}
                    </li>
                  ))}
                </ul>
              </div>
              <div className="bg-emerald-50 rounded-2xl border border-emerald-200 p-4">
                <h4 className="text-xs font-bold text-emerald-600 uppercase tracking-wider mb-3">
                  Safe Injection Windows
                </h4>
                <ul className="space-y-1.5">
                  {prescanResult.safe_windows.map((w: string, i: number) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-emerald-800">
                      <span className="text-emerald-500 flex-shrink-0">✓</span>{w}
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {/* Abort criteria */}
            <div className="bg-red-50 rounded-2xl border border-red-200 p-4">
              <h4 className="text-xs font-bold text-red-600 uppercase tracking-wider mb-3">
                Abort Criteria — Do Not Inject If:
              </h4>
              <ul className="space-y-1.5">
                {prescanResult.abort_criteria.map((c: string, i: number) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-red-700">
                    <span className="flex-shrink-0 font-bold">✗</span>{c}
                  </li>
                ))}
              </ul>
            </div>

            {/* Junior note */}
            {prescanResult.junior_note && (
              <div className="bg-violet-50 rounded-xl border border-violet-200 px-4 py-3">
                <p className="text-xs text-violet-700">{prescanResult.junior_note}</p>
              </div>
            )}

            {/* Evidence note */}
            <div className="bg-slate-50 rounded-xl border border-slate-200 px-4 py-3">
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Evidence Base</p>
              <p className="text-xs text-slate-600">{prescanResult.evidence_note}</p>
            </div>

            {/* Disclaimer */}
            <p className="text-[10px] text-slate-400 leading-relaxed px-1">
              {prescanResult.disclaimer}
            </p>
          </>
        )}
      </div>
    </div>
  );
}

export default PreScanBriefingTab;
