import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Loader2, GitCompare, FileText, Users, Download, BookOpen, Check, Copy, Bell } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { getToken } from "@/lib/auth";

interface ComparisonData {
  comparison_table?: Array<{ attribute: string; values: Record<string, string> }>;
  summary?: string;
  key_differences?: string[];
  clinical_pearls?: string[];
}

interface ComparisonResponse {
  comparison: ComparisonData;
  citations: Citation[];
  view: string;
  cached: boolean;
}

interface ProtocolResponse {
  protocol: string;
  citations: Citation[];
  view: string;
  cached: boolean;
}

interface HandoutResponse {
  handout: string;
  topic: string;
  language: string;
  reading_level: string;
  citations: Citation[];
  view: string;
  cached: boolean;
}

interface Citation {
  title?: string;
  journal?: string;
  year?: number;
  doi?: string;
  url?: string;
  authors?: string[];
  first_author?: string;
  source_type?: string;
  evidence_level?: string;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  
  const handleCopy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  
  return (
    <Button variant="outline" size="sm" onClick={handleCopy} data-testid="button-copy">
      {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
      {copied ? "Copied" : "Copy"}
    </Button>
  );
}

function CitationsList({ citations }: { citations: Citation[] }) {
  return (
    <div className="mt-4 space-y-2">
      <h4 className="font-medium text-sm text-muted-foreground">Sources</h4>
      <div className="space-y-1">
        {citations.map((c, i) => (
          <div key={i} className="text-sm">
            <Badge variant="outline" className="mr-2">{i + 1}</Badge>
            <span>{c.title}</span>
            {c.year && <span className="text-muted-foreground"> ({c.year})</span>}
            {c.journal && <span className="text-muted-foreground"> - {c.journal}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

function TreatmentCompareForm() {
  const { toast } = useToast();
  const [treatments, setTreatments] = useState<string[]>(["", ""]);
  const [context, setContext] = useState("");
  const [result, setResult] = useState<ComparisonResponse | null>(null);
  
  const mutation = useMutation({
    mutationFn: async () => {
      const validTreatments = treatments.filter(t => t.trim());
      if (validTreatments.length < 2) {
        throw new Error("At least 2 treatments required");
      }
      
      const res = await fetch("/api/compare", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          treatments: validTreatments,
          context: context || undefined,
        }),
      });
      
      if (!res.ok) throw new Error("Failed to generate comparison");
      return res.json() as Promise<ComparisonResponse>;
    },
    onSuccess: (data) => {
      setResult(data);
      toast({ 
        title: "Comparison generated", 
        description: data.cached ? "Retrieved from cache" : "Fresh analysis complete"
      });
    },
    onError: (err: Error) => {
      toast({ variant: "destructive", title: "Error", description: err.message });
    },
  });
  
  const addTreatment = () => {
    if (treatments.length < 4) {
      setTreatments([...treatments, ""]);
    }
  };
  
  const updateTreatment = (index: number, value: string) => {
    const updated = [...treatments];
    updated[index] = value;
    setTreatments(updated);
  };
  
  const removeTreatment = (index: number) => {
    if (treatments.length > 2) {
      setTreatments(treatments.filter((_, i) => i !== index));
    }
  };
  
  return (
    <div className="space-y-4">
      <div className="space-y-3">
        <Label>Treatments to Compare (2-4)</Label>
        {treatments.map((t, i) => (
          <div key={i} className="flex gap-2">
            <Input
              placeholder={`Treatment ${i + 1} (e.g., Botox, Dysport)`}
              value={t}
              onChange={(e) => updateTreatment(i, e.target.value)}
              data-testid={`input-treatment-${i}`}
            />
            {treatments.length > 2 && (
              <Button variant="ghost" size="icon" onClick={() => removeTreatment(i)}>
                ×
              </Button>
            )}
          </div>
        ))}
        {treatments.length < 4 && (
          <Button variant="outline" size="sm" onClick={addTreatment}>
            + Add Treatment
          </Button>
        )}
      </div>
      
      <div className="space-y-2">
        <Label htmlFor="context">Clinical Context (optional)</Label>
        <Input
          id="context"
          placeholder="e.g., glabellar lines in male patient, forehead treatment"
          value={context}
          onChange={(e) => setContext(e.target.value)}
          data-testid="input-compare-context"
        />
      </div>
      
      <Button 
        onClick={() => mutation.mutate()} 
        disabled={mutation.isPending}
        className="w-full"
        data-testid="button-compare"
      >
        {mutation.isPending ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Analyzing...
          </>
        ) : (
          <>
            <GitCompare className="mr-2 h-4 w-4" />
            Compare Treatments
          </>
        )}
      </Button>
      
      {result && (
        <div className="mt-6 space-y-4 border-t pt-4">
          <div className="flex justify-between items-center">
            <h3 className="font-semibold">Comparison Results</h3>
            {result.cached && <Badge variant="secondary">Cached</Badge>}
          </div>
          
          {result.comparison.comparison_table && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="border-b">
                    <th className="text-left p-2 font-medium">Attribute</th>
                    {Object.keys(result.comparison.comparison_table[0]?.values || {}).map(t => (
                      <th key={t} className="text-left p-2 font-medium">{t}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.comparison.comparison_table.map((row, i) => (
                    <tr key={i} className="border-b">
                      <td className="p-2 font-medium">{row.attribute}</td>
                      {Object.values(row.values).map((v, j) => (
                        <td key={j} className="p-2">{v}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          
          {result.comparison.summary && (
            <div>
              <h4 className="font-medium mb-2">Summary</h4>
              <p className="text-sm text-muted-foreground">{result.comparison.summary}</p>
            </div>
          )}
          
          {result.comparison.clinical_pearls && result.comparison.clinical_pearls.length > 0 && (
            <div>
              <h4 className="font-medium mb-2">Clinical Pearls</h4>
              <ul className="list-disc list-inside text-sm space-y-1">
                {result.comparison.clinical_pearls.map((pearl, i) => (
                  <li key={i}>{pearl}</li>
                ))}
              </ul>
            </div>
          )}
          
          <CitationsList citations={result.citations} />
        </div>
      )}
    </div>
  );
}

function TreatmentProtocolForm() {
  const { toast } = useToast();
  const [topic, setTopic] = useState("");
  const [patientProfile, setPatientProfile] = useState("");
  const [result, setResult] = useState<ProtocolResponse | null>(null);
  
  const mutation = useMutation({
    mutationFn: async () => {
      if (!topic.trim()) throw new Error("Topic required");
      
      const res = await fetch("/api/protocol", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          topic,
          patient_profile: patientProfile || undefined,
        }),
      });
      
      if (!res.ok) throw new Error("Failed to generate protocol");
      return res.json() as Promise<ProtocolResponse>;
    },
    onSuccess: (data) => {
      setResult(data);
      toast({ title: "Protocol generated" });
    },
    onError: (err: Error) => {
      toast({ variant: "destructive", title: "Error", description: err.message });
    },
  });
  
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="protocol-topic">Treatment Topic *</Label>
        <Input
          id="protocol-topic"
          placeholder="e.g., Botox glabellar injection, lip filler with cannula"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          data-testid="input-protocol-topic"
        />
      </div>
      
      <div className="space-y-2">
        <Label htmlFor="patient-profile">Patient Profile (optional)</Label>
        <Input
          id="patient-profile"
          placeholder="e.g., 45yo female, first treatment, moderate wrinkles"
          value={patientProfile}
          onChange={(e) => setPatientProfile(e.target.value)}
          data-testid="input-patient-profile"
        />
      </div>
      
      <Button 
        onClick={() => mutation.mutate()} 
        disabled={mutation.isPending || !topic.trim()}
        className="w-full"
        data-testid="button-generate-protocol"
      >
        {mutation.isPending ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Generating...
          </>
        ) : (
          <>
            <BookOpen className="mr-2 h-4 w-4" />
            Generate Protocol
          </>
        )}
      </Button>
      
      {result && (
        <div className="mt-6 space-y-4 border-t pt-4">
          <div className="flex justify-between items-center">
            <h3 className="font-semibold">Treatment Protocol</h3>
            <CopyButton text={result.protocol} />
          </div>
          
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <pre className="whitespace-pre-wrap text-sm bg-muted p-4 rounded-lg">
              {result.protocol}
            </pre>
          </div>
          
          <CitationsList citations={result.citations} />
        </div>
      )}
    </div>
  );
}

function PatientHandoutForm() {
  const { toast } = useToast();
  const [topic, setTopic] = useState("");
  const [language, setLanguage] = useState("en");
  const [readingLevel, setReadingLevel] = useState("middle_school");
  const [result, setResult] = useState<HandoutResponse | null>(null);
  
  const mutation = useMutation({
    mutationFn: async () => {
      if (!topic.trim()) throw new Error("Topic required");
      
      const res = await fetch("/api/handout", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          topic,
          language,
          reading_level: readingLevel,
        }),
      });
      
      if (!res.ok) throw new Error("Failed to generate handout");
      return res.json() as Promise<HandoutResponse>;
    },
    onSuccess: (data) => {
      setResult(data);
      toast({ title: "Handout generated" });
    },
    onError: (err: Error) => {
      toast({ variant: "destructive", title: "Error", description: err.message });
    },
  });
  
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="handout-topic">Treatment/Procedure *</Label>
        <Input
          id="handout-topic"
          placeholder="e.g., Botox treatment, dermal filler aftercare"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          data-testid="input-handout-topic"
        />
      </div>
      
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label>Language</Label>
          <Select value={language} onValueChange={setLanguage}>
            <SelectTrigger data-testid="select-handout-language">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="en">English</SelectItem>
              <SelectItem value="es">Spanish</SelectItem>
              <SelectItem value="fr">French</SelectItem>
              <SelectItem value="de">German</SelectItem>
              <SelectItem value="zh">Chinese</SelectItem>
              <SelectItem value="ja">Japanese</SelectItem>
              <SelectItem value="ko">Korean</SelectItem>
              <SelectItem value="ar">Arabic</SelectItem>
              <SelectItem value="pt">Portuguese</SelectItem>
              <SelectItem value="ru">Russian</SelectItem>
            </SelectContent>
          </Select>
        </div>
        
        <div className="space-y-2">
          <Label>Reading Level</Label>
          <Select value={readingLevel} onValueChange={setReadingLevel}>
            <SelectTrigger data-testid="select-reading-level">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="simple">Simple (5th grade)</SelectItem>
              <SelectItem value="middle_school">Standard (8th grade)</SelectItem>
              <SelectItem value="high_school">Detailed (12th grade)</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      
      <Button 
        onClick={() => mutation.mutate()} 
        disabled={mutation.isPending || !topic.trim()}
        className="w-full"
        data-testid="button-generate-handout"
      >
        {mutation.isPending ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Generating...
          </>
        ) : (
          <>
            <Users className="mr-2 h-4 w-4" />
            Generate Patient Handout
          </>
        )}
      </Button>
      
      {result && (
        <div className="mt-6 space-y-4 border-t pt-4">
          <div className="flex justify-between items-center">
            <h3 className="font-semibold">Patient Handout</h3>
            <CopyButton text={result.handout} />
          </div>
          
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <pre className="whitespace-pre-wrap text-sm bg-muted p-4 rounded-lg">
              {result.handout}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

function CitationExportForm() {
  const { toast } = useToast();
  const [citations, setCitations] = useState("");
  const [format, setFormat] = useState("bibtex");
  
  const mutation = useMutation({
    mutationFn: async () => {
      let parsed: Citation[];
      try {
        parsed = JSON.parse(citations);
        if (!Array.isArray(parsed)) throw new Error("Must be an array");
      } catch {
        throw new Error("Invalid JSON - paste citations array from search results");
      }
      
      const res = await fetch("/api/export-citations", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${getToken()}`,
        },
        body: JSON.stringify({ citations: parsed, format }),
      });
      
      if (!res.ok) throw new Error("Export failed");
      
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = format === "bibtex" ? "citations.bib" : "citations.ris";
      a.click();
      URL.revokeObjectURL(url);
    },
    onSuccess: () => {
      toast({ title: "Citations exported", description: `Downloaded as ${format.toUpperCase()}` });
    },
    onError: (err: Error) => {
      toast({ variant: "destructive", title: "Error", description: err.message });
    },
  });
  
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label>Citations JSON</Label>
        <Textarea
          placeholder='Paste citations array from search results, e.g.:\n[{"title": "...", "year": 2023, "journal": "..."}]'
          value={citations}
          onChange={(e) => setCitations(e.target.value)}
          rows={6}
          data-testid="textarea-citations"
        />
        <p className="text-xs text-muted-foreground">
          Copy citations from any AesthetiCite search result and paste here
        </p>
      </div>
      
      <div className="space-y-2">
        <Label>Export Format</Label>
        <Select value={format} onValueChange={setFormat}>
          <SelectTrigger data-testid="select-export-format">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="bibtex">BibTeX (.bib)</SelectItem>
            <SelectItem value="ris">RIS (.ris)</SelectItem>
          </SelectContent>
        </Select>
      </div>
      
      <Button 
        onClick={() => mutation.mutate()} 
        disabled={mutation.isPending || !citations.trim()}
        className="w-full"
        data-testid="button-export-citations"
      >
        {mutation.isPending ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Exporting...
          </>
        ) : (
          <>
            <Download className="mr-2 h-4 w-4" />
            Export Citations
          </>
        )}
      </Button>
    </div>
  );
}

function ResearchAlertsForm() {
  const { toast } = useToast();
  const [topics, setTopics] = useState<string[]>([""]);
  
  const addMutation = useMutation({
    mutationFn: async () => {
      const validTopics = topics.filter(t => t.trim());
      if (validTopics.length === 0) throw new Error("At least one topic required");
      
      const res = await fetch("/api/interests", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          topics: validTopics,
          action: "add",
        }),
      });
      
      if (!res.ok) throw new Error("Failed to save interests");
      return res.json();
    },
    onSuccess: () => {
      toast({ title: "Research interests saved", description: "You'll receive weekly email digests" });
    },
    onError: (err: Error) => {
      toast({ variant: "destructive", title: "Error", description: err.message });
    },
  });
  
  const addTopic = () => {
    setTopics([...topics, ""]);
  };
  
  const updateTopic = (index: number, value: string) => {
    const updated = [...topics];
    updated[index] = value;
    setTopics(updated);
  };
  
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Set up personalized alerts for research topics you care about. You'll receive weekly email digests with new papers matching your interests.
      </p>
      
      <div className="space-y-3">
        <Label>Research Topics</Label>
        {topics.map((t, i) => (
          <Input
            key={i}
            placeholder={`Topic ${i + 1} (e.g., botulinum toxin, filler complications)`}
            value={t}
            onChange={(e) => updateTopic(i, e.target.value)}
            data-testid={`input-alert-topic-${i}`}
          />
        ))}
        <Button variant="outline" size="sm" onClick={addTopic}>
          + Add Topic
        </Button>
      </div>
      
      <Button 
        onClick={() => addMutation.mutate()} 
        disabled={addMutation.isPending}
        className="w-full"
        data-testid="button-save-alerts"
      >
        {addMutation.isPending ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Saving...
          </>
        ) : (
          <>
            <Bell className="mr-2 h-4 w-4" />
            Save Research Alerts
          </>
        )}
      </Button>
    </div>
  );
}

export default function ResearchToolsPage() {
  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-5xl p-6">
        <div className="mb-8">
          <h1 className="text-3xl font-bold">Research & Comparison Tools</h1>
          <p className="text-muted-foreground mt-2">
            Evidence-based treatment comparisons, protocols, patient handouts, and research alerts.
          </p>
        </div>
        
        <Tabs defaultValue="compare" className="space-y-6">
          <TabsList className="grid w-full grid-cols-5">
            <TabsTrigger value="compare" className="flex gap-2" data-testid="tab-compare">
              <GitCompare className="h-4 w-4" />
              <span className="hidden md:inline">Compare</span>
            </TabsTrigger>
            <TabsTrigger value="protocol" className="flex gap-2" data-testid="tab-protocol">
              <BookOpen className="h-4 w-4" />
              <span className="hidden md:inline">Protocol</span>
            </TabsTrigger>
            <TabsTrigger value="handout" className="flex gap-2" data-testid="tab-handout">
              <Users className="h-4 w-4" />
              <span className="hidden md:inline">Handout</span>
            </TabsTrigger>
            <TabsTrigger value="export" className="flex gap-2" data-testid="tab-export">
              <Download className="h-4 w-4" />
              <span className="hidden md:inline">Export</span>
            </TabsTrigger>
            <TabsTrigger value="alerts" className="flex gap-2" data-testid="tab-alerts">
              <Bell className="h-4 w-4" />
              <span className="hidden md:inline">Alerts</span>
            </TabsTrigger>
          </TabsList>
          
          <TabsContent value="compare">
            <Card>
              <CardHeader>
                <CardTitle>Treatment Comparison</CardTitle>
                <CardDescription>
                  Compare 2-4 treatments side-by-side with evidence-based analysis including dosing, onset, duration, and contraindications.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <TreatmentCompareForm />
              </CardContent>
            </Card>
          </TabsContent>
          
          <TabsContent value="protocol">
            <Card>
              <CardHeader>
                <CardTitle>Treatment Protocol Generator</CardTitle>
                <CardDescription>
                  Generate step-by-step treatment protocols with dosing ranges, technique, follow-up, and complication management.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <TreatmentProtocolForm />
              </CardContent>
            </Card>
          </TabsContent>
          
          <TabsContent value="handout">
            <Card>
              <CardHeader>
                <CardTitle>Patient Handout Generator</CardTitle>
                <CardDescription>
                  Create patient education handouts in multiple languages at appropriate reading levels.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <PatientHandoutForm />
              </CardContent>
            </Card>
          </TabsContent>
          
          <TabsContent value="export">
            <Card>
              <CardHeader>
                <CardTitle>Citation Export</CardTitle>
                <CardDescription>
                  Export citations in BibTeX or RIS format for reference managers (Zotero, EndNote, Mendeley).
                </CardDescription>
              </CardHeader>
              <CardContent>
                <CitationExportForm />
              </CardContent>
            </Card>
          </TabsContent>
          
          <TabsContent value="alerts">
            <Card>
              <CardHeader>
                <CardTitle>Research Alerts</CardTitle>
                <CardDescription>
                  Set up personalized email digests for new research on topics you care about.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ResearchAlertsForm />
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
