import { Link } from "wouter";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Shield, FileText, BookOpen, CheckCircle, ArrowRight, Download, Mail } from "lucide-react";

type Feature = { title: string; desc: string; icon: typeof Shield };
type Step = { title: string; desc: string };

const features: Feature[] = [
  {
    title: "Evidence Strength Summary (always visible)",
    desc: "Confidence score (0-10), highest evidence level, evidence mix, and explicit evidence gaps — shown before the answer.",
    icon: Shield,
  },
  {
    title: "Strict citation discipline",
    desc: "No citation = no claim. Every factual statement is tied to an inline source marker.",
    icon: CheckCircle,
  },
  {
    title: "Governance-first structure",
    desc: "Answers are formatted as a clinical governance note: key points, safety, limitations, and follow-up questions.",
    icon: FileText,
  },
  {
    title: "Audit-friendly continuity",
    desc: "Persistent conversation history and exportable usage reporting for structured pilot evaluation.",
    icon: BookOpen,
  },
];

const pilotSteps: Step[] = [
  { title: "Week 1", desc: "Set up 5 seats, align governance objectives, and define clinic-specific evaluation metrics." },
  { title: "Weeks 2-7", desc: "Live usage with weekly metrics. Governance review at day 30 to refine workflows." },
  { title: "Week 8", desc: "Final evaluation report: usage, evidence mix, recurrent themes, and governance recommendations." },
];

function SectionDivider() {
  return <div className="my-12 h-px w-full bg-border" />;
}

function SectionTitle({ eyebrow, title, desc }: { eyebrow?: string; title: string; desc?: string }) {
  return (
    <div className="max-w-3xl">
      {eyebrow && (
        <div className="text-xs font-semibold tracking-widest text-muted-foreground uppercase" data-testid={`text-eyebrow-${eyebrow.toLowerCase()}`}>
          {eyebrow}
        </div>
      )}
      <h2 className="mt-2 text-2xl font-semibold md:text-3xl">{title}</h2>
      {desc && <p className="mt-3 text-base leading-7 text-muted-foreground">{desc}</p>}
    </div>
  );
}

function InfoCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="p-6">
      <div className="text-sm font-semibold">{title}</div>
      <div className="mt-2 text-sm leading-6 text-muted-foreground">{children}</div>
    </Card>
  );
}

export default function GovernancePage() {
  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-50 border-b bg-background/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-center gap-3">
            <img
              src="/aestheticite-logo.png"
              alt="AesthetiCite"
              className="w-9 h-9 object-contain rounded-lg"
              data-testid="img-governance-logo"
            />
            <div className="leading-tight">
              <div className="text-sm font-semibold" data-testid="text-brand-name">AesthetiCite</div>
              <div className="text-xs text-muted-foreground">Clinical Evidence Governance</div>
            </div>
          </div>

          <nav className="hidden items-center gap-6 md:flex">
            <a className="text-sm text-muted-foreground hover-elevate rounded-md px-2 py-1" href="#governance" data-testid="link-nav-governance">
              Governance
            </a>
            <a className="text-sm text-muted-foreground hover-elevate rounded-md px-2 py-1" href="#output" data-testid="link-nav-output">
              Output
            </a>
            <a className="text-sm text-muted-foreground hover-elevate rounded-md px-2 py-1" href="#pilot" data-testid="link-nav-pilot">
              Pilot
            </a>
            <a className="text-sm text-muted-foreground hover-elevate rounded-md px-2 py-1" href="#trust" data-testid="link-nav-trust">
              Trust
            </a>
          </nav>

          <div className="flex items-center gap-2">
            <Link href="/login">
              <Button variant="outline" data-testid="button-sign-in">
                Sign in
              </Button>
            </Link>
            <a href="#request">
              <Button data-testid="button-request-pilot">
                Request pilot
              </Button>
            </a>
          </div>
        </div>
      </header>

      <main>
        <section className="mx-auto max-w-6xl px-4 py-12 md:py-16">
          <div className="flex flex-col gap-8 md:flex-row md:items-center md:justify-between">
            <div className="max-w-2xl">
              <div className="flex flex-wrap gap-2">
                <Badge variant="outline" data-testid="badge-clinic-networks">Built for aesthetic clinic networks</Badge>
                <Badge variant="outline" data-testid="badge-traceability">Evidence traceability</Badge>
                <Badge variant="outline" data-testid="badge-conservative">Conservative output</Badge>
              </div>

              <h1 className="mt-5 text-3xl font-semibold tracking-tight md:text-5xl" data-testid="text-hero-headline">
                Clinical evidence governance for aesthetic medicine
              </h1>

              <p className="mt-5 text-base leading-7 text-muted-foreground md:text-lg" data-testid="text-hero-description">
                AesthetiCite standardizes evidence interpretation across multi-site practices with strict citation
                discipline, visible evidence strength, and conservative safety framing — designed to reinforce clinical
                documentation and governance workflows.
              </p>

              <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
                <a href="#request">
                  <Button data-testid="button-request-pilot-hero">
                    Request a 60-day governance pilot
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </Button>
                </a>
                <a href="#output">
                  <Button variant="outline" data-testid="button-see-output">
                    See structured output
                  </Button>
                </a>
              </div>

              <p className="mt-4 text-xs leading-5 text-muted-foreground" data-testid="text-disclaimer">
                Educational decision support. Not a substitute for clinical judgment. No patient-identifiable data
                required.
              </p>
            </div>

            <div className="w-full md:w-[420px] flex-shrink-0">
              <Card className="p-4" data-testid="card-evidence-summary">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-semibold">Evidence Strength Summary</div>
                  <Badge variant="secondary" className="text-xs" data-testid="badge-sample">Sample</Badge>
                </div>

                <div className="mt-3 grid grid-cols-2 gap-3">
                  <div className="rounded-lg border p-3">
                    <div className="text-[11px] text-muted-foreground">Confidence</div>
                    <div className="mt-1 text-lg font-semibold" data-testid="text-confidence-value">8.6 / 10</div>
                  </div>
                  <div className="rounded-lg border p-3">
                    <div className="text-[11px] text-muted-foreground">Highest level</div>
                    <div className="mt-1 text-sm font-semibold" data-testid="text-highest-level">Guideline / Consensus</div>
                  </div>
                  <div className="rounded-lg border p-3">
                    <div className="text-[11px] text-muted-foreground">Sources used</div>
                    <div className="mt-1 text-lg font-semibold" data-testid="text-sources-count">12</div>
                  </div>
                  <div className="rounded-lg border p-3">
                    <div className="text-[11px] text-muted-foreground">Evidence mix</div>
                    <div className="mt-1 text-sm font-semibold" data-testid="text-evidence-mix">Guidelines &bull; SR &bull; RCT</div>
                  </div>
                </div>

                <div className="mt-4 rounded-lg border p-3">
                  <div className="text-[11px] font-semibold">Evidence gaps</div>
                  <div className="mt-1 text-sm text-muted-foreground" data-testid="text-evidence-gaps">
                    Limited high-quality comparative data for specific off-label technique variants.
                  </div>
                </div>

                <div className="mt-4 rounded-lg border p-3">
                  <div className="text-[11px] font-semibold">Key points (excerpt)</div>
                  <ul className="mt-2 space-y-2 text-sm" data-testid="list-key-points">
                    <li className="leading-6">
                      Conservative technique and clear risk screening are emphasized in consensus guidance.{" "}
                      <span className="font-mono text-xs text-muted-foreground">[S1][S3]</span>
                    </li>
                    <li className="leading-6">
                      Uncertainty is stated explicitly when evidence is limited.{" "}
                      <span className="font-mono text-xs text-muted-foreground">[S2]</span>
                    </li>
                  </ul>
                </div>

                <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
                  <div>Inline citations</div>
                  <div className="font-mono">No cite = no claim</div>
                </div>
              </Card>
            </div>
          </div>

          <SectionDivider />

          <section id="governance" className="py-2">
            <SectionTitle
              eyebrow="Governance"
              title="Designed for standardization, auditability, and conservative clinical support"
              desc="Aesthetics is high-stakes and reputation-sensitive. Governance requires traceability, controlled language, and consistent documentation norms across sites."
            />

            <div className="mt-8 grid gap-4 md:grid-cols-2">
              {features.map((f, i) => (
                <Card key={i} className="p-6 hover-elevate" data-testid={`card-feature-${i}`}>
                  <div className="flex items-start gap-3">
                    <f.icon className="h-5 w-5 text-muted-foreground flex-shrink-0 mt-0.5" />
                    <div>
                      <div className="text-sm font-semibold">{f.title}</div>
                      <div className="mt-2 text-sm leading-6 text-muted-foreground">{f.desc}</div>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          </section>

          <SectionDivider />

          <section id="output" className="py-2">
            <SectionTitle
              eyebrow="Structured output"
              title="It should read like a governance note — not a chat conversation"
              desc="The first screen should communicate evidence strength, what is well-supported, and what remains uncertain — before any detailed discussion."
            />

            <div className="mt-8 grid gap-4 lg:grid-cols-3">
              <InfoCard title="Clinical Summary">
                2-3 lines only. Conservative language. No overclaiming.
              </InfoCard>
              <InfoCard title="Key Evidence-Based Points">
                Bullet points ending with multi-source citations.
              </InfoCard>
              <InfoCard title="Safety + Limitations">
                Safety is explicit. Evidence gaps are stated plainly.
              </InfoCard>
            </div>

            <div className="mt-8 rounded-md border p-6 bg-secondary/50">
              <div className="text-sm font-semibold">Output design principles</div>
              <ul className="mt-3 space-y-2 text-sm leading-6 text-muted-foreground" data-testid="list-output-principles">
                <li className="flex items-start gap-2">
                  <CheckCircle className="h-4 w-4 mt-0.5 flex-shrink-0 text-muted-foreground" />
                  Structured report-style output with visible confidence, evidence level, gaps, and citations.
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle className="h-4 w-4 mt-0.5 flex-shrink-0 text-muted-foreground" />
                  Governance and risk framing over marketing language.
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle className="h-4 w-4 mt-0.5 flex-shrink-0 text-muted-foreground" />
                  Conservative uncertainty handling — what is not known is stated explicitly.
                </li>
              </ul>
            </div>
          </section>

          <SectionDivider />

          <section id="pilot" className="py-2">
            <SectionTitle
              eyebrow="Pilot"
              title="60-day governance pilot for clinic networks"
              desc="Designed to be measurable and low-friction: multi-seat access, usage analytics, and a structured evaluation report."
            />

            <div className="mt-8 grid gap-4 md:grid-cols-3">
              {pilotSteps.map((s, i) => (
                <Card key={i} className="p-6" data-testid={`card-pilot-step-${i}`}>
                  <div className="text-xs font-semibold tracking-widest text-muted-foreground uppercase">{s.title}</div>
                  <div className="mt-2 text-sm leading-6 text-muted-foreground">{s.desc}</div>
                </Card>
              ))}
            </div>

            <div className="mt-8 grid gap-4 md:grid-cols-2">
              <InfoCard title="Included">
                <ul className="mt-1 list-disc pl-5 space-y-1">
                  <li>5 clinical seats</li>
                  <li>Evidence mix and citation-density analytics</li>
                  <li>Mid-point governance review (day 30)</li>
                  <li>Final evaluation report (day 60)</li>
                </ul>
              </InfoCard>
              <InfoCard title="Pilot outcomes">
                <ul className="mt-1 list-disc pl-5 space-y-1">
                  <li>Measurable adoption (questions per clinician)</li>
                  <li>Topics map (what clinicians actually need)</li>
                  <li>Governance recommendations</li>
                  <li>Case study pathway (with permission)</li>
                </ul>
              </InfoCard>
            </div>
          </section>

          <SectionDivider />

          <section id="trust" className="py-2">
            <SectionTitle
              eyebrow="Trust"
              title="Conservative by design"
              desc="Healthcare governance rewards restraint. AesthetiCite is designed to prioritize traceability and explicit limitations."
            />

            <div className="mt-8 grid gap-4 md:grid-cols-2">
              <InfoCard title="Clinical responsibility">
                Educational decision support. Not a substitute for clinician judgment. Output reflects retrieved sources only.
              </InfoCard>
              <InfoCard title="Data handling">
                No patient-identifiable data required. Conversations may be stored for continuity and audit review within the organization.
              </InfoCard>
              <InfoCard title="Citation integrity">
                No cite = no claim. If evidence is insufficient, the system states "Evidence insufficient" rather than guessing.
              </InfoCard>
              <InfoCard title="Institutional reporting">
                Usage metrics, evidence-type distribution, and exportable pilot reporting support governance evaluation.
              </InfoCard>
            </div>
          </section>

          <SectionDivider />

          <section id="request" className="py-2">
            <SectionTitle
              eyebrow="Request pilot"
              title="Request a governance pilot for your clinic network"
              desc="Short discovery call first. We align on governance objectives and confirm suitability for a controlled evaluation."
            />

            <div className="mt-8 grid gap-4 md:grid-cols-2">
              <Card className="p-6" data-testid="card-contact">
                <div className="flex items-center gap-2">
                  <Mail className="h-4 w-4 text-muted-foreground" />
                  <div className="text-sm font-semibold">Contact</div>
                </div>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  Use a direct email to the Medical Director / Clinical Governance Lead.
                  Keep it discovery-oriented and governance-framed.
                </p>

                <div className="mt-4 rounded-md bg-secondary/50 p-4">
                  <div className="text-xs font-semibold">Email snippet (copy-ready)</div>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground" data-testid="text-email-snippet">
                    Hello Dr [Name],<br />
                    I'm reaching out regarding a governance-oriented evidence support platform designed for multi-site
                    aesthetic clinics. It provides conservative, citation-disciplined outputs with visible evidence
                    strength and explicit limitations to support documentation consistency across sites.<br /><br />
                    Would you be open to a brief 15-minute call to understand how your group standardizes evidence-based
                    practice and complication readiness?<br /><br />
                    Kind regards,<br />
                    Youssef Lidary
                  </p>
                </div>
              </Card>

              <Card className="p-6" data-testid="card-pilot-assets">
                <div className="flex items-center gap-2">
                  <Download className="h-4 w-4 text-muted-foreground" />
                  <div className="text-sm font-semibold">Pilot assets</div>
                </div>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  For enterprise perception, always provide a formal overview PDF before the demo.
                </p>
                <div className="mt-4 flex flex-col gap-2">
                  <Button variant="outline" className="justify-start" data-testid="button-download-governance-pdf">
                    <FileText className="h-4 w-4 mr-2" />
                    Governance Overview (PDF)
                  </Button>
                  <Button variant="outline" className="justify-start" data-testid="button-download-pilot-pdf">
                    <FileText className="h-4 w-4 mr-2" />
                    60-Day Pilot Structure (PDF)
                  </Button>
                  <Button variant="outline" className="justify-start" data-testid="button-download-privacy-pdf">
                    <FileText className="h-4 w-4 mr-2" />
                    Data Handling & Privacy (PDF)
                  </Button>
                </div>
              </Card>
            </div>
          </section>

          <footer className="mt-16 border-t py-10" data-testid="section-footer">
            <div className="mx-auto max-w-6xl">
              <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
                <div className="text-sm text-muted-foreground">
                  &copy; {new Date().getFullYear()} AesthetiCite — Clinical Evidence Governance
                </div>
                <div className="flex gap-4 text-sm">
                  <a className="text-muted-foreground hover-elevate rounded-md px-2 py-1" href="/terms" data-testid="link-terms">
                    Terms
                  </a>
                  <a className="text-muted-foreground hover-elevate rounded-md px-2 py-1" href="/privacy" data-testid="link-privacy">
                    Privacy
                  </a>
                  <a className="text-muted-foreground hover-elevate rounded-md px-2 py-1" href="/contact" data-testid="link-contact">
                    Contact
                  </a>
                </div>
              </div>
            </div>
          </footer>
        </section>
      </main>
    </div>
  );
}
