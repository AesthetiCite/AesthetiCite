import { useState, useRef, useCallback } from "react";
import { Link, useLocation } from "wouter";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ThemeToggle } from "@/components/theme-toggle";
import { BRAND } from "@/config";
import { getToken } from "@/lib/auth";
import {
  Play, Loader2, CheckCircle, AlertTriangle, Trophy, ChevronDown, ChevronUp,
  Zap, FlaskConical, Brain, Shield, BookOpen, ArrowLeft, RotateCcw, Sparkles, Clock
} from "lucide-react";
import { cn } from "@/lib/utils";

function formatMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

const QUESTIONS: Array<{
  id: number;
  question: string;
  category: string;
  difficulty: "hard" | "critical";
  icon: React.ReactNode;
  generalResponse: string;
  advantage: string[];
}> = [
  {
    id: 1,
    question: "What are the early signs of vascular compromise during HA filler injection and what should be done immediately?",
    category: "Vascular Emergency",
    difficulty: "critical",
    icon: <AlertTriangle className="w-4 h-4" />,
    generalResponse:
      "Vascular compromise during hyaluronic acid filler injection can present with blanching or whitening of the skin, pain disproportionate to the procedure, and livedo reticularis. If these signs occur, the injection should be stopped immediately. Hyaluronidase should be considered if the filler is HA-based. The patient should be monitored and referred to appropriate emergency services if symptoms progress. Warm compresses and massage may be applied. Ocular symptoms warrant urgent ophthalmologic evaluation.",
    advantage: [
      "Triggers full Vascular Occlusion Protocol with time-stamped action sequence",
      "Differentiates blanching vs livedo vs mottling with separate action trees",
      "Procedure-specific insight (tear trough vs nasolabial vs glabellar territory)",
      "Integrates hyaluronidase_helper inline tool with dose estimation",
      "Evidence-graded from Consensus + PI sources (not general dermatology)",
    ],
  },
  {
    id: 2,
    question: "Tear trough filler: what safety considerations and risk mitigation are emphasized in the literature?",
    category: "Anatomy & Safety",
    difficulty: "critical",
    icon: <Shield className="w-4 h-4" />,
    generalResponse:
      "The tear trough region is a delicate area for filler injection. Key considerations include the proximity to the angular vein and infraorbital vessels, which increases the risk of vascular compromise. Literature recommends using lower-viscosity HA fillers placed in the preperiosteal plane, with small volumes and slow injection technique. Tyndall effect (bluish discoloration) is a common complication due to superficial placement. Patient selection is critical, as patients with thin skin or significant tear trough deformity may have higher complication rates.",
    advantage: [
      "Loads tear_trough_ha_filler Procedure Intelligence block with zone-specific anatomy",
      "Classifies periorbital territory as vision-threatening — triggers elevated safety framing",
      "Cites aesthetic-specific consensus (ISAPS, ACCS) not general dermatology guidelines",
      "Provides injection plane decision tree (supraperiosteal vs deep dermal)",
      "ACI score reflects evidence quality specifically for periorbital aesthetic literature",
    ],
  },
  {
    id: 3,
    question: "Glabellar injections: what makes this zone higher risk and what precautions are recommended?",
    category: "Anatomy & Risk",
    difficulty: "critical",
    icon: <Brain className="w-4 h-4" />,
    generalResponse:
      "The glabellar region carries elevated risk due to the presence of the supratrochlear and supraorbital arteries, which have direct connections to the ophthalmic artery. Retrograde embolism in this area can cause vision loss. FDA guidance explicitly warns against injecting fillers into the glabella. Precautions include using small volumes, avoiding deep injections, using blunt cannulas, and aspirating before injection where clinically appropriate.",
    advantage: [
      "Separates glabellar filler vs glabellar toxin into distinct Procedure Intelligence profiles",
      "Includes ophthalmic territory mapping with supratrochlear + supraorbital danger zones",
      "Toxin ptosis protocol triggered automatically for glabellar toxin queries",
      "Evidence hierarchy distinguishes FDA contraindication (PI) from consensus guidance",
      "Numeric guardrail: flags any dose/volume that exceeds safe published thresholds",
    ],
  },
  {
    id: 4,
    question: "How should suspected ocular symptoms after filler injection be handled according to consensus guidance?",
    category: "Ocular Emergency",
    difficulty: "critical",
    icon: <AlertTriangle className="w-4 h-4" />,
    generalResponse:
      "Ocular symptoms following filler injection (such as sudden visual changes, diplopia, or vision loss) represent a medical emergency. The patient should be immediately transferred to hospital for ophthalmologic assessment. High-dose hyaluronidase may be administered if the injection was HA-based. Retrobulbar hyaluronidase injection has been proposed but carries significant risks. Early treatment within minutes to hours is critical for visual recovery.",
    advantage: [
      "Activates Vascular Occlusion Protocol with vision-loss branch and ophthalmology escalation timer",
      "Differentiates retrobulbar vs systemic hyaluronidase with evidence strength per approach",
      "Time-budgeted: 'within 60–90 minutes' framing pulled from consensus sources, not inferred",
      "ocular_symptom flag auto-detected in clinical context — changes answer structure",
      "Conflict detection: flags disagreement between high-dose vs titrated hyaluronidase approaches",
    ],
  },
  {
    id: 5,
    question: "How should a clinic structure an emergency response for suspected HA filler vascular compromise?",
    category: "Protocol & Preparation",
    difficulty: "hard",
    icon: <FlaskConical className="w-4 h-4" />,
    generalResponse:
      "Clinics performing filler injections should have an emergency protocol in place. This includes having hyaluronidase readily available, knowing the nearest emergency ophthalmology service, and training staff in recognizing vascular compromise. A written protocol should document steps for managing complications, including when to administer hyaluronidase, how to document the event, and when to transfer the patient. Regular simulation training is recommended.",
    advantage: [
      "Generates structured 6-step emergency protocol from consensus evidence, not generic advice",
      "POST /api/complications/log-case ready: response feeds directly into case documentation",
      "Includes pre-procedural checklist, intra-procedural recognition, and post-event documentation",
      "Role-specific guidance: injector vs nurse vs clinic coordinator actions",
      "PDF protocol card exportable for wall-mounting — from /api/complications/export-pdf",
    ],
  },
  {
    id: 6,
    question: "What does the evidence say about the role of hyaluronidase in HA filler complications?",
    category: "Evidence Grading",
    difficulty: "hard",
    icon: <BookOpen className="w-4 h-4" />,
    generalResponse:
      "Hyaluronidase is an enzyme that degrades hyaluronic acid and is the primary treatment for HA filler-related vascular complications. Evidence from case reports and consensus guidelines supports its use in managing vascular occlusion, Tyndall effect, and delayed nodules. Dosing varies widely in published literature, ranging from 20 to 1500 units depending on the indication and clinical judgment. Allergy testing prior to use is recommended by some authors, though this is not universally practiced.",
    advantage: [
      "Evidence tiered by source: distinguishes PI-level (manufacturer) vs RCT vs expert consensus",
      "ACI sub-scores: citation density 0.42 weight applied to hyaluronidase evidence pool",
      "hyaluronidase_helper inline tool triggered — real-time dose range pulled from Prescribing Info",
      "Freshness score computed: alerts if dominant sources are >5 years old for this fast-moving topic",
      "Conflict detection: flags the 'test dose vs no test dose' disagreement between guidelines",
    ],
  },
  {
    id: 7,
    question: "If a 100U vial is reconstituted with 2.5 mL, what is the concentration in U/mL and U per 0.1 mL?",
    category: "Dosing Mathematics",
    difficulty: "hard",
    icon: <Zap className="w-4 h-4" />,
    generalResponse:
      "If a 100-unit vial is reconstituted with 2.5 mL of normal saline, the concentration would be 40 units per mL (100 ÷ 2.5 = 40 U/mL). Therefore, each 0.1 mL would contain 4 units. This is a common dilution for botulinum toxin type A used in aesthetic practice. The appropriate dilution depends on the specific product, indication, and practitioner preference.",
    advantage: [
      "botox_dilution_helper inline tool triggered — validates the math against PI-approved reconstitution",
      "Computes the full dilution table: 1mL, 2mL, 2.5mL, 4mL — not just the asked value",
      "Adds clinical note: 40U/mL vs 50U/mL vs 25U/mL comparative spread-diffusion implications",
      "Hallucination kill-switch: if math contradicts PI range, answer is blocked and flagged",
      "Source-grounded: references Botox/Dysport/Xeomin PI, not inferred from general pharmacology",
    ],
  },
  {
    id: 8,
    question: "Laser treatments in Fitzpatrick IV-VI: what risk mitigation is commonly recommended to reduce PIH?",
    category: "Energy Devices",
    difficulty: "hard",
    icon: <Zap className="w-4 h-4" />,
    generalResponse:
      "Patients with Fitzpatrick skin types IV-VI are at increased risk of post-inflammatory hyperpigmentation (PIH) following laser treatments. Risk mitigation strategies include pre-treatment skin priming with topical agents such as hydroquinone, retinoids, or azelaic acid for 4–6 weeks before the procedure. Conservative laser parameters (lower fluence, longer pulse width) should be used. Test spots in a non-visible area are recommended before full treatment. Strict sun avoidance and broad-spectrum SPF 50+ are essential in the post-procedure period.",
    advantage: [
      "Retrieves from 17,000+ aesthetic device publications — Fitzpatrick IV-VI literature prioritized",
      "Evidence freshness: alerts if PIH evidence is pre-2020 (active research area)",
      "Separates ablative vs non-ablative vs fractional laser recommendations by evidence tier",
      "Compares topical pre-treatment options with Level I vs III evidence labels",
      "Aesthetic-aware retrieval boost: 'Fitzpatrick dark skin laser' queries get specialist chunk pool",
    ],
  },
  {
    id: 9,
    question: "How should clinicians think about on-label vs off-label use in aesthetic medicine when communicating risk?",
    category: "Regulatory",
    difficulty: "hard",
    icon: <Shield className="w-4 h-4" />,
    generalResponse:
      "Off-label use of medications and devices is common in aesthetic medicine. Clinicians should document informed consent specifically addressing the off-label nature of the treatment. Patients should understand that off-label use means the treatment has not been approved by regulatory agencies for that specific indication, though the product itself is approved. Clinicians should be familiar with local regulatory requirements and professional body guidance regarding off-label practice. Good clinical reasoning and evidence of efficacy should support the decision.",
    advantage: [
      "Distinguishes CE mark (EU/UK) vs FDA approval vs TGA vs Health Canada — jurisdiction-aware",
      "Regulatory alignment check embedded in every answer: flags where aesthetics-specific guidance conflicts",
      "Avoids overclaiming: CE vs FDA language guardrail prevents wrong regulatory framing by region",
      "Consent documentation notes auto-generated with off-label risk framing",
      "Evidence base limited to peer-reviewed aesthetic publications — not general drug law commentary",
    ],
  },
  {
    id: 10,
    question: "When should an injector stop the procedure and escalate based on perfusion changes?",
    category: "Clinical Decision",
    difficulty: "critical",
    icon: <AlertTriangle className="w-4 h-4" />,
    generalResponse:
      "An injector should stop the procedure immediately if the patient reports sudden severe pain, if there is visible blanching or livedo reticularis at the injection site, or if there are any complaints of visual symptoms. Escalation should occur if blanching does not resolve with massage within a few minutes, or if livedo reticularis spreads. The patient should be transferred to an emergency facility if there is any suspicion of significant vascular compromise, particularly if visual symptoms are present.",
    advantage: [
      "Threshold-specific: 'blanching >10 minutes without improvement → escalate' pulled from consensus",
      "capillary_refill_delayed and skin_color_change ClinicalContext fields change protocol branch",
      "Multi-signal decision tree: pain_score + color_change + cap_refill + timeline → tiered action",
      "Separates 'stop and observe' from 'stop and treat now' from 'stop and call 999/112/911'",
      "Answer section 4 'What can go wrong next?' specifically models post-stop complication cascade",
    ],
  },
];

type QuestionState = {
  status: "idle" | "running" | "done" | "error";
  answer: string;
  aciScore: number | null;
  citations: number;
  evidenceBadge: string | null;
  expanded: boolean;
  latencyMs: number | null;
  elapsedMs: number;
};

function DifficultyBadge({ difficulty }: { difficulty: "hard" | "critical" }) {
  return (
    <Badge
      className={cn(
        "text-xs font-semibold",
        difficulty === "critical"
          ? "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300"
          : "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300"
      )}
    >
      {difficulty === "critical" ? "Critical" : "Hard"}
    </Badge>
  );
}

function AciBar({ score }: { score: number }) {
  const pct = Math.round(score * 10);
  const color =
    score >= 0.8 ? "bg-emerald-500" : score >= 0.55 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-muted-foreground w-8 shrink-0">ACI</span>
      <div className="flex-1 bg-muted rounded-full h-1.5">
        <div className={cn("h-1.5 rounded-full transition-all", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-mono font-medium w-10 text-right">{score.toFixed(2)}</span>
    </div>
  );
}

function QuestionCard({
  q,
  state,
  onRun,
  onReset,
}: {
  q: (typeof QUESTIONS)[0];
  state: QuestionState;
  onRun: () => void;
  onReset: () => void;
}) {
  const [advExpanded, setAdvExpanded] = useState(false);

  return (
    <Card
      className={cn(
        "border transition-all duration-200",
        state.status === "running" && "border-primary/40 shadow-md",
        state.status === "done" && "border-emerald-500/30"
      )}
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0">
            <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary text-sm font-bold">
              {q.id}
            </div>
            <div className="min-w-0">
              <CardTitle className="text-sm leading-snug font-medium" data-testid={`question-${q.id}-text`}>
                {q.question}
              </CardTitle>
              <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                <DifficultyBadge difficulty={q.difficulty} />
                <Badge variant="outline" className="text-xs gap-1">
                  {q.icon}
                  {q.category}
                </Badge>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            {state.status === "done" && (
              <Button
                variant="ghost"
                size="sm"
                className="h-8 w-8 p-0"
                onClick={onReset}
                data-testid={`reset-${q.id}`}
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </Button>
            )}
            <Button
              size="sm"
              onClick={onRun}
              disabled={state.status === "running"}
              data-testid={`run-question-${q.id}`}
              className={cn(
                "gap-1.5 font-mono tabular-nums",
                state.status === "done" && "bg-emerald-600 hover:bg-emerald-700 text-white"
              )}
            >
              {state.status === "running" ? (
                <><Loader2 className="w-3.5 h-3.5 animate-spin" /> {formatMs(state.elapsedMs)}</>
              ) : state.status === "done" ? (
                <><CheckCircle className="w-3.5 h-3.5" /> {state.latencyMs !== null ? formatMs(state.latencyMs) : "Done"}</>
              ) : (
                <><Play className="w-3.5 h-3.5" /> Ask AesthetiCite</>
              )}
            </Button>
          </div>
        </div>
      </CardHeader>

      {(state.status !== "idle") && (
        <CardContent className="pt-0 space-y-4">
          <div className="grid md:grid-cols-2 gap-3">
            {/* AesthetiCite column */}
            <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
              <div className="flex items-center gap-1.5 mb-2">
                <Sparkles className="w-3.5 h-3.5 text-primary" />
                <span className="text-xs font-semibold text-primary">AesthetiCite</span>
                {state.evidenceBadge && (
                  <Badge variant="outline" className="text-xs ml-auto border-primary/30 text-primary">
                    {state.evidenceBadge}
                  </Badge>
                )}
              </div>

              {state.status === "running" && state.answer === "" && (
                <div className="flex items-center justify-between py-4 text-muted-foreground text-xs">
                  <div className="flex items-center gap-2">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    Retrieving evidence…
                  </div>
                  <span className="font-mono tabular-nums text-foreground/60">{formatMs(state.elapsedMs)}</span>
                </div>
              )}

              {state.answer && (
                <ScrollArea className="max-h-56">
                  <p className="text-xs leading-relaxed text-foreground whitespace-pre-wrap" data-testid={`answer-${q.id}`}>
                    {state.answer}
                    {state.status === "running" && (
                      <span className="inline-block w-1.5 h-3 bg-primary ml-0.5 animate-pulse" />
                    )}
                  </p>
                </ScrollArea>
              )}

              {state.status === "done" && (
                <div className="mt-2 space-y-1.5 border-t border-primary/20 pt-2">
                  {state.aciScore !== null && <AciBar score={state.aciScore} />}
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <div className="flex items-center gap-1">
                      <BookOpen className="w-3 h-3" />
                      {state.citations} citations
                    </div>
                    {state.latencyMs !== null && (
                      <div className="flex items-center gap-1 font-mono font-medium text-foreground" data-testid={`latency-${q.id}`}>
                        <Clock className="w-3 h-3 text-muted-foreground" />
                        {formatMs(state.latencyMs)}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {state.status === "error" && (
                <p className="text-xs text-destructive">API unavailable — Python still loading. Try again in 60s.</p>
              )}
            </div>

            {/* General AI column */}
            <div className="rounded-lg border bg-muted/30 p-3">
              <div className="flex items-center gap-1.5 mb-2">
                <Brain className="w-3.5 h-3.5 text-muted-foreground" />
                <span className="text-xs font-semibold text-muted-foreground">General AI Response</span>
                <Badge variant="secondary" className="text-xs ml-auto">Representative</Badge>
              </div>
              <ScrollArea className="max-h-56">
                <p className="text-xs leading-relaxed text-muted-foreground">{q.generalResponse}</p>
              </ScrollArea>
            </div>
          </div>

          {/* AesthetiCite Advantages */}
          <div className="rounded-lg border border-emerald-500/20 bg-emerald-50/50 dark:bg-emerald-950/20 p-3">
            <button
              className="flex items-center justify-between w-full text-left"
              onClick={() => setAdvExpanded(!advExpanded)}
              data-testid={`toggle-advantages-${q.id}`}
            >
              <div className="flex items-center gap-1.5">
                <Trophy className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                  Why AesthetiCite goes further ({q.advantage.length})
                </span>
              </div>
              {advExpanded ? (
                <ChevronUp className="w-3.5 h-3.5 text-emerald-600" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5 text-emerald-600" />
              )}
            </button>
            {advExpanded && (
              <ul className="mt-2 space-y-1">
                {q.advantage.map((adv, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-xs text-emerald-800 dark:text-emerald-200">
                    <CheckCircle className="w-3 h-3 mt-0.5 shrink-0 text-emerald-600" />
                    {adv}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </CardContent>
      )}
    </Card>
  );
}

export default function Hardest10Page() {
  const [, setLocation] = useLocation();
  const [states, setStates] = useState<Record<number, QuestionState>>(
    Object.fromEntries(
      QUESTIONS.map((q) => [
        q.id,
        { status: "idle", answer: "", aciScore: null, citations: 0, evidenceBadge: null, expanded: false, latencyMs: null, elapsedMs: 0 },
      ])
    )
  );
  const [runningAll, setRunningAll] = useState(false);
  const abortRefs = useRef<Record<number, AbortController>>({});
  const startTimeRefs = useRef<Record<number, number>>({});
  const tickerRefs = useRef<Record<number, ReturnType<typeof setInterval>>>({});

  const updateState = useCallback((id: number, patch: Partial<QuestionState>) => {
    setStates((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  }, []);

  const stopTicker = useCallback((qid: number) => {
    if (tickerRefs.current[qid]) {
      clearInterval(tickerRefs.current[qid]);
      delete tickerRefs.current[qid];
    }
  }, []);

  const runQuestion = useCallback(
    async (qid: number) => {
      const token = getToken();
      if (!token) {
        setLocation("/login");
        return;
      }

      abortRefs.current[qid]?.abort();
      stopTicker(qid);
      const ctl = new AbortController();
      abortRefs.current[qid] = ctl;

      const t0 = Date.now();
      startTimeRefs.current[qid] = t0;

      updateState(qid, { status: "running", answer: "", aciScore: null, citations: 0, evidenceBadge: null, latencyMs: null, elapsedMs: 0 });

      tickerRefs.current[qid] = setInterval(() => {
        const elapsed = Date.now() - startTimeRefs.current[qid];
        setStates((prev) => ({
          ...prev,
          [qid]: { ...prev[qid], elapsedMs: elapsed },
        }));
      }, 100);

      const question = QUESTIONS.find((q) => q.id === qid)!.question;

      try {
        const res = await fetch("/api/v2/stream", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ question, domain: "aesthetic_medicine", mode: "standard" }),
          signal: ctl.signal,
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const reader = res.body?.getReader();
        if (!reader) throw new Error("No body");

        const decoder = new TextDecoder();
        let buffer = "";
        let fullText = "";

        while (true) {
          if (ctl.signal.aborted) break;
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            try {
              const data = JSON.parse(line.slice(6));
              if (data.type === "content" && typeof data.data === "string") {
                fullText += data.data;
                updateState(qid, { answer: fullText });
              } else if (data.type === "citations") {
                const raw = data.aci_score;
                const aci =
                  raw && typeof raw === "object" ? raw.overall_confidence_0_10 : raw;
                updateState(qid, {
                  citations: (data.citations || []).length,
                  aciScore: typeof aci === "number" ? aci / 10 : null,
                });
              } else if (data.type === "badge") {
                updateState(qid, { evidenceBadge: data.data || null });
              }
            } catch {}
          }
        }

        stopTicker(qid);
        const finalMs = Date.now() - t0;
        updateState(qid, { status: "done", latencyMs: finalMs, elapsedMs: finalMs });
      } catch (err: unknown) {
        stopTicker(qid);
        if ((err as Error)?.name === "AbortError") return;
        updateState(qid, { status: "error", latencyMs: Date.now() - t0 });
      }
    },
    [updateState, setLocation, stopTicker]
  );

  const resetQuestion = useCallback(
    (qid: number) => {
      abortRefs.current[qid]?.abort();
      stopTicker(qid);
      updateState(qid, {
        status: "idle",
        answer: "",
        aciScore: null,
        citations: 0,
        evidenceBadge: null,
        latencyMs: null,
        elapsedMs: 0,
      });
    },
    [updateState, stopTicker]
  );

  const runAll = useCallback(async () => {
    setRunningAll(true);
    for (const q of QUESTIONS) {
      if (states[q.id].status === "done") continue;
      await runQuestion(q.id);
      await new Promise((r) => setTimeout(r, 800));
    }
    setRunningAll(false);
  }, [runQuestion, states]);

  const doneCount = Object.values(states).filter((s) => s.status === "done").length;
  const avgAci =
    Object.values(states)
      .filter((s) => s.aciScore !== null)
      .reduce((acc, s) => acc + (s.aciScore || 0), 0) /
    Math.max(1, Object.values(states).filter((s) => s.aciScore !== null).length);
  const latencyValues = Object.values(states).filter((s) => s.latencyMs !== null).map((s) => s.latencyMs as number);
  const avgLatencyMs = latencyValues.length > 0 ? Math.round(latencyValues.reduce((a, b) => a + b, 0) / latencyValues.length) : null;

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b bg-card/50 backdrop-blur sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <Link href="/">
              <Button variant="ghost" size="sm" className="gap-1.5 shrink-0" data-testid="back-home">
                <ArrowLeft className="w-4 h-4" />
                Back
              </Button>
            </Link>
            <div className="min-w-0">
              <h1 className="font-bold text-lg leading-tight" data-testid="page-title">
                10 Hardest Questions — vs General AI
              </h1>
              <p className="text-xs text-muted-foreground truncate">
                {BRAND.name} live answers • Critical aesthetic medicine scenarios
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-6 space-y-6">
        {/* Stats banner */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="rounded-lg border bg-card p-3 text-center" data-testid="stat-done">
            <div className="text-2xl font-bold text-primary">{doneCount}/{QUESTIONS.length}</div>
            <div className="text-xs text-muted-foreground">Questions Run</div>
          </div>
          <div className="rounded-lg border bg-card p-3 text-center" data-testid="stat-aci">
            <div className={cn("text-2xl font-bold", doneCount > 0 ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground")}>
              {doneCount > 0 ? avgAci.toFixed(2) : "—"}
            </div>
            <div className="text-xs text-muted-foreground">Avg ACI Score</div>
          </div>
          <div className="rounded-lg border bg-card p-3 text-center" data-testid="stat-latency">
            <div className={cn("text-2xl font-bold font-mono tabular-nums", avgLatencyMs !== null ? "text-blue-600 dark:text-blue-400" : "text-muted-foreground")}>
              {avgLatencyMs !== null ? formatMs(avgLatencyMs) : "—"}
            </div>
            <div className="text-xs text-muted-foreground">Avg Response Time</div>
          </div>
          <div className="rounded-lg border bg-card p-3 text-center" data-testid="stat-critical">
            <div className="text-2xl font-bold text-red-600 dark:text-red-400">
              {QUESTIONS.filter((q) => q.difficulty === "critical").length}
            </div>
            <div className="text-xs text-muted-foreground">Critical Scenarios</div>
          </div>
        </div>

        {/* Control bar */}
        <div className="flex items-center justify-between gap-3 p-4 rounded-lg border bg-card/60">
          <div className="text-sm text-muted-foreground max-w-md">
            Each question runs{" "}
            <span className="font-medium text-foreground">live against {BRAND.name}</span> with
            real retrieval, ACI scoring, and complication protocol detection. The right column shows
            a representative general-AI response for comparison.
          </div>
          <Button
            onClick={runAll}
            disabled={runningAll || doneCount === QUESTIONS.length}
            className="gap-2 shrink-0"
            data-testid="run-all-button"
          >
            {runningAll ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> Running all…</>
            ) : (
              <><Play className="w-4 h-4" /> Run All 10</>
            )}
          </Button>
        </div>

        {/* Question cards */}
        <div className="space-y-4">
          {QUESTIONS.map((q) => (
            <QuestionCard
              key={q.id}
              q={q}
              state={states[q.id]}
              onRun={() => runQuestion(q.id)}
              onReset={() => resetQuestion(q.id)}
            />
          ))}
        </div>

        {/* Footer note */}
        <p className="text-xs text-center text-muted-foreground pb-6">
          General AI responses are representative examples showing typical output from general medical AI tools — not verbatim OpenEvidence output.
          {BRAND.name} responses are fully live from the real API with 217K+ publications.
        </p>
      </main>
    </div>
  );
}
