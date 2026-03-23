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
import { Loader2, FileText, ClipboardList, Stethoscope, FileOutput, Copy, Check, Mic, MicOff } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { getToken } from "@/lib/auth";

interface PriorAuthResponse {
  letter: string;
  icd10_codes: string[];
  cpt_codes: string[];
}

interface PatientInstructionResponse {
  title: string;
  instructions: string;
  warnings?: string;
  follow_up?: string;
  emergency_signs?: string;
}

interface ICD10Code {
  code: string;
  description: string;
  confidence: string;
}

interface ICD10Response {
  primary_diagnosis: ICD10Code;
  secondary_diagnoses: ICD10Code[];
  rule_out_diagnoses: ICD10Code[];
}

interface DischargeSummaryResponse {
  summary: string;
  icd10_codes: string[];
  cpt_codes: string[];
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

function PriorAuthForm() {
  const { toast } = useToast();
  const [result, setResult] = useState<PriorAuthResponse | null>(null);
  const [urgency, setUrgency] = useState("routine");
  
  const mutation = useMutation({
    mutationFn: async (formData: FormData) => {
      const data = {
        patient_name: formData.get("patient_name") as string,
        patient_dob: formData.get("patient_dob") as string,
        insurance_company: formData.get("insurance_company") as string,
        insurance_id: formData.get("insurance_id") as string,
        diagnosis: formData.get("diagnosis") as string,
        procedure: formData.get("procedure") as string,
        clinical_justification: formData.get("clinical_justification") as string,
        physician_name: formData.get("physician_name") as string,
        physician_npi: formData.get("physician_npi") as string || undefined,
        urgency: urgency,
      };
      
      const res = await fetch("/api/clinical-docs/prior-auth", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${getToken()}`,
        },
        body: JSON.stringify(data),
      });
      
      if (!res.ok) throw new Error("Failed to generate prior authorization");
      return res.json() as Promise<PriorAuthResponse>;
    },
    onSuccess: (data) => {
      setResult(data);
      toast({ title: "Prior authorization letter generated" });
    },
    onError: () => {
      toast({ title: "Failed to generate letter", variant: "destructive" });
    },
  });
  
  return (
    <div className="space-y-6">
      <form onSubmit={(e) => { e.preventDefault(); mutation.mutate(new FormData(e.currentTarget)); }} className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="patient_name">Patient Name</Label>
            <Input id="patient_name" name="patient_name" required data-testid="input-patient-name" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="patient_dob">Date of Birth</Label>
            <Input id="patient_dob" name="patient_dob" type="date" required data-testid="input-patient-dob" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="insurance_company">Insurance Company</Label>
            <Input id="insurance_company" name="insurance_company" required data-testid="input-insurance-company" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="insurance_id">Insurance ID</Label>
            <Input id="insurance_id" name="insurance_id" required data-testid="input-insurance-id" />
          </div>
        </div>
        
        <div className="space-y-2">
          <Label htmlFor="diagnosis">Diagnosis</Label>
          <Input id="diagnosis" name="diagnosis" required data-testid="input-diagnosis" />
        </div>
        
        <div className="space-y-2">
          <Label htmlFor="procedure">Requested Procedure</Label>
          <Input id="procedure" name="procedure" required data-testid="input-procedure" />
        </div>
        
        <div className="space-y-2">
          <Label htmlFor="clinical_justification">Clinical Justification</Label>
          <Textarea id="clinical_justification" name="clinical_justification" rows={4} required data-testid="input-justification" />
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="space-y-2">
            <Label htmlFor="physician_name">Physician Name</Label>
            <Input id="physician_name" name="physician_name" required data-testid="input-physician-name" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="physician_npi">NPI (Optional)</Label>
            <Input id="physician_npi" name="physician_npi" data-testid="input-physician-npi" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="urgency">Urgency</Label>
            <Select value={urgency} onValueChange={setUrgency}>
              <SelectTrigger data-testid="select-urgency">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="routine">Routine</SelectItem>
                <SelectItem value="urgent">Urgent</SelectItem>
                <SelectItem value="emergent">Emergent</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        
        <Button type="submit" disabled={mutation.isPending} data-testid="button-generate-prior-auth">
          {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Generate Prior Authorization
        </Button>
      </form>
      
      {result && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-4">
            <CardTitle>Generated Letter</CardTitle>
            <CopyButton text={result.letter} />
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="whitespace-pre-wrap text-sm bg-muted p-4 rounded-lg">{result.letter}</div>
            <div className="flex flex-wrap gap-2">
              <span className="text-sm font-medium">ICD-10:</span>
              {result.icd10_codes.map((code) => (
                <Badge key={code} variant="secondary">{code}</Badge>
              ))}
            </div>
            <div className="flex flex-wrap gap-2">
              <span className="text-sm font-medium">CPT:</span>
              {result.cpt_codes.map((code) => (
                <Badge key={code} variant="outline">{code}</Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function PatientInstructionsForm() {
  const { toast } = useToast();
  const [result, setResult] = useState<PatientInstructionResponse | null>(null);
  const [language, setLanguage] = useState("en");
  const [readingLevel, setReadingLevel] = useState("6th grade");
  
  const mutation = useMutation({
    mutationFn: async (formData: FormData) => {
      const data = {
        procedure: formData.get("procedure") as string,
        diagnosis: formData.get("diagnosis") as string || undefined,
        language: language,
        reading_level: readingLevel,
        include_warnings: true,
        include_follow_up: true,
      };
      
      const res = await fetch("/api/clinical-docs/patient-instructions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${getToken()}`,
        },
        body: JSON.stringify(data),
      });
      
      if (!res.ok) throw new Error("Failed to generate instructions");
      return res.json() as Promise<PatientInstructionResponse>;
    },
    onSuccess: (data) => {
      setResult(data);
      toast({ title: "Patient instructions generated" });
    },
    onError: () => {
      toast({ title: "Failed to generate instructions", variant: "destructive" });
    },
  });
  
  const fullText = result ? `${result.title}\n\n${result.instructions}\n\n${result.warnings || ""}\n\n${result.follow_up || ""}\n\n${result.emergency_signs || ""}` : "";
  
  return (
    <div className="space-y-6">
      <form onSubmit={(e) => { e.preventDefault(); mutation.mutate(new FormData(e.currentTarget)); }} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="procedure">Procedure / Treatment</Label>
          <Input id="procedure" name="procedure" placeholder="e.g., Botox injection, Dental crown" required data-testid="input-procedure-instructions" />
        </div>
        
        <div className="space-y-2">
          <Label htmlFor="diagnosis">Diagnosis (Optional)</Label>
          <Input id="diagnosis" name="diagnosis" placeholder="e.g., Facial wrinkles, Tooth decay" data-testid="input-diagnosis-instructions" />
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="language">Language</Label>
            <Select value={language} onValueChange={setLanguage}>
              <SelectTrigger data-testid="select-language">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="en">English</SelectItem>
                <SelectItem value="es">Spanish</SelectItem>
                <SelectItem value="fr">French</SelectItem>
                <SelectItem value="de">German</SelectItem>
                <SelectItem value="pt">Portuguese</SelectItem>
                <SelectItem value="ar">Arabic</SelectItem>
                <SelectItem value="zh">Chinese</SelectItem>
                <SelectItem value="hi">Hindi</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="reading_level">Reading Level</Label>
            <Select value={readingLevel} onValueChange={setReadingLevel}>
              <SelectTrigger data-testid="select-reading-level">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="4th grade">4th Grade</SelectItem>
                <SelectItem value="6th grade">6th Grade</SelectItem>
                <SelectItem value="8th grade">8th Grade</SelectItem>
                <SelectItem value="high school">High School</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        
        <Button type="submit" disabled={mutation.isPending} data-testid="button-generate-instructions">
          {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Generate Instructions
        </Button>
      </form>
      
      {result && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-4">
            <CardTitle>{result.title}</CardTitle>
            <CopyButton text={fullText} />
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="prose prose-sm dark:prose-invert max-w-none">
              <p className="whitespace-pre-wrap">{result.instructions}</p>
              {result.warnings && (
                <div className="p-3 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg border border-yellow-200 dark:border-yellow-800">
                  <h4 className="font-semibold text-yellow-800 dark:text-yellow-200">Warnings</h4>
                  <p className="whitespace-pre-wrap text-yellow-700 dark:text-yellow-300">{result.warnings}</p>
                </div>
              )}
              {result.follow_up && (
                <div>
                  <h4 className="font-semibold">Follow-up Care</h4>
                  <p className="whitespace-pre-wrap">{result.follow_up}</p>
                </div>
              )}
              {result.emergency_signs && (
                <div className="p-3 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800">
                  <h4 className="font-semibold text-red-800 dark:text-red-200">When to Seek Emergency Care</h4>
                  <p className="whitespace-pre-wrap text-red-700 dark:text-red-300">{result.emergency_signs}</p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function ICD10CodesForm() {
  const { toast } = useToast();
  const [result, setResult] = useState<ICD10Response | null>(null);
  const [specialty, setSpecialty] = useState("general");
  
  const mutation = useMutation({
    mutationFn: async (formData: FormData) => {
      const data = {
        clinical_notes: formData.get("clinical_notes") as string,
        specialty: specialty,
      };
      
      const res = await fetch("/api/clinical-docs/icd10-codes", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${getToken()}`,
        },
        body: JSON.stringify(data),
      });
      
      if (!res.ok) throw new Error("Failed to suggest codes");
      return res.json() as Promise<ICD10Response>;
    },
    onSuccess: (data) => {
      setResult(data);
      toast({ title: "ICD-10 codes suggested" });
    },
    onError: () => {
      toast({ title: "Failed to suggest codes", variant: "destructive" });
    },
  });
  
  const confidenceColor = (confidence: string) => {
    switch (confidence) {
      case "high": return "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300";
      case "medium": return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300";
      default: return "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300";
    }
  };
  
  return (
    <div className="space-y-6">
      <form onSubmit={(e) => { e.preventDefault(); mutation.mutate(new FormData(e.currentTarget)); }} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="clinical_notes">Clinical Notes</Label>
          <Textarea 
            id="clinical_notes" 
            name="clinical_notes" 
            rows={6} 
            placeholder="Enter clinical notes, chief complaint, history, and assessment..."
            required 
            data-testid="input-clinical-notes"
          />
        </div>
        
        <div className="space-y-2">
          <Label htmlFor="specialty">Specialty</Label>
          <Select value={specialty} onValueChange={setSpecialty}>
            <SelectTrigger data-testid="select-specialty">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="general">General Medicine</SelectItem>
              <SelectItem value="aesthetic">Aesthetic Medicine</SelectItem>
              <SelectItem value="dental">Dental Medicine</SelectItem>
              <SelectItem value="dermatology">Dermatology</SelectItem>
              <SelectItem value="cardiology">Cardiology</SelectItem>
              <SelectItem value="orthopedics">Orthopedics</SelectItem>
              <SelectItem value="neurology">Neurology</SelectItem>
            </SelectContent>
          </Select>
        </div>
        
        <Button type="submit" disabled={mutation.isPending} data-testid="button-suggest-codes">
          {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Suggest ICD-10 Codes
        </Button>
      </form>
      
      {result && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Primary Diagnosis</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-3">
                <Badge variant="default" className="text-base">{result.primary_diagnosis.code}</Badge>
                <span>{result.primary_diagnosis.description}</span>
                <Badge className={confidenceColor(result.primary_diagnosis.confidence)}>
                  {result.primary_diagnosis.confidence}
                </Badge>
              </div>
            </CardContent>
          </Card>
          
          {result.secondary_diagnoses.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Secondary Diagnoses</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {result.secondary_diagnoses.map((dx, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <Badge variant="secondary">{dx.code}</Badge>
                    <span className="text-sm">{dx.description}</span>
                    <Badge className={confidenceColor(dx.confidence)}>{dx.confidence}</Badge>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
          
          {result.rule_out_diagnoses.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Rule Out Diagnoses</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {result.rule_out_diagnoses.map((dx, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <Badge variant="outline">{dx.code}</Badge>
                    <span className="text-sm">{dx.description}</span>
                    <Badge className={confidenceColor(dx.confidence)}>{dx.confidence}</Badge>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}

function DischargeSummaryForm() {
  const { toast } = useToast();
  const [result, setResult] = useState<DischargeSummaryResponse | null>(null);
  const [procedures, setProcedures] = useState<string[]>([""]);
  const [medications, setMedications] = useState<string[]>([""]);
  
  const mutation = useMutation({
    mutationFn: async (formData: FormData) => {
      const data = {
        patient_name: formData.get("patient_name") as string,
        admission_date: formData.get("admission_date") as string,
        discharge_date: formData.get("discharge_date") as string,
        admitting_diagnosis: formData.get("admitting_diagnosis") as string,
        procedures_performed: procedures.filter(p => p.trim()),
        hospital_course: formData.get("hospital_course") as string,
        discharge_diagnosis: formData.get("discharge_diagnosis") as string,
        medications: medications.filter(m => m.trim()),
        follow_up_instructions: formData.get("follow_up_instructions") as string,
        physician_name: formData.get("physician_name") as string,
      };
      
      const res = await fetch("/api/clinical-docs/discharge-summary", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${getToken()}`,
        },
        body: JSON.stringify(data),
      });
      
      if (!res.ok) throw new Error("Failed to generate summary");
      return res.json() as Promise<DischargeSummaryResponse>;
    },
    onSuccess: (data) => {
      setResult(data);
      toast({ title: "Discharge summary generated" });
    },
    onError: () => {
      toast({ title: "Failed to generate summary", variant: "destructive" });
    },
  });
  
  return (
    <div className="space-y-6">
      <form onSubmit={(e) => { e.preventDefault(); mutation.mutate(new FormData(e.currentTarget)); }} className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="space-y-2">
            <Label htmlFor="patient_name">Patient Name</Label>
            <Input id="patient_name" name="patient_name" required data-testid="input-discharge-patient" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="admission_date">Admission Date</Label>
            <Input id="admission_date" name="admission_date" type="date" required data-testid="input-admission-date" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="discharge_date">Discharge Date</Label>
            <Input id="discharge_date" name="discharge_date" type="date" required data-testid="input-discharge-date" />
          </div>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="admitting_diagnosis">Admitting Diagnosis</Label>
            <Input id="admitting_diagnosis" name="admitting_diagnosis" required data-testid="input-admitting-diagnosis" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="discharge_diagnosis">Discharge Diagnosis</Label>
            <Input id="discharge_diagnosis" name="discharge_diagnosis" required data-testid="input-discharge-diagnosis" />
          </div>
        </div>
        
        <div className="space-y-2">
          <Label>Procedures Performed</Label>
          {procedures.map((proc, i) => (
            <div key={i} className="flex gap-2">
              <Input 
                value={proc}
                onChange={(e) => {
                  const newProcs = [...procedures];
                  newProcs[i] = e.target.value;
                  setProcedures(newProcs);
                }}
                placeholder={`Procedure ${i + 1}`}
                data-testid={`input-procedure-${i}`}
              />
              {i === procedures.length - 1 && (
                <Button type="button" variant="outline" onClick={() => setProcedures([...procedures, ""])}>+</Button>
              )}
            </div>
          ))}
        </div>
        
        <div className="space-y-2">
          <Label htmlFor="hospital_course">Hospital Course</Label>
          <Textarea id="hospital_course" name="hospital_course" rows={4} required data-testid="input-hospital-course" />
        </div>
        
        <div className="space-y-2">
          <Label>Discharge Medications</Label>
          {medications.map((med, i) => (
            <div key={i} className="flex gap-2">
              <Input 
                value={med}
                onChange={(e) => {
                  const newMeds = [...medications];
                  newMeds[i] = e.target.value;
                  setMedications(newMeds);
                }}
                placeholder={`Medication ${i + 1}`}
                data-testid={`input-medication-${i}`}
              />
              {i === medications.length - 1 && (
                <Button type="button" variant="outline" onClick={() => setMedications([...medications, ""])}>+</Button>
              )}
            </div>
          ))}
        </div>
        
        <div className="space-y-2">
          <Label htmlFor="follow_up_instructions">Follow-up Instructions</Label>
          <Textarea id="follow_up_instructions" name="follow_up_instructions" rows={2} required data-testid="input-follow-up" />
        </div>
        
        <div className="space-y-2">
          <Label htmlFor="physician_name">Attending Physician</Label>
          <Input id="physician_name" name="physician_name" required data-testid="input-attending-physician" />
        </div>
        
        <Button type="submit" disabled={mutation.isPending} data-testid="button-generate-discharge">
          {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Generate Discharge Summary
        </Button>
      </form>
      
      {result && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-4">
            <CardTitle>Discharge Summary</CardTitle>
            <CopyButton text={result.summary} />
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="whitespace-pre-wrap text-sm bg-muted p-4 rounded-lg">{result.summary}</div>
            <div className="flex flex-wrap gap-2">
              <span className="text-sm font-medium">ICD-10:</span>
              {result.icd10_codes.map((code) => (
                <Badge key={code} variant="secondary">{code}</Badge>
              ))}
            </div>
            <div className="flex flex-wrap gap-2">
              <span className="text-sm font-medium">CPT:</span>
              {result.cpt_codes.map((code) => (
                <Badge key={code} variant="outline">{code}</Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function VoiceTranscriptionForm() {
  const { toast } = useToast();
  const [isRecording, setIsRecording] = useState(false);
  const [mediaRecorder, setMediaRecorder] = useState<MediaRecorder | null>(null);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [transcript, setTranscript] = useState("");
  
  const mutation = useMutation({
    mutationFn: async (blob: Blob) => {
      const formData = new FormData();
      formData.append("file", blob, "recording.webm");
      
      const res = await fetch("/api/voice/transcribe", {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${getToken()}`,
        },
        body: formData,
      });
      
      if (!res.ok) throw new Error("Transcription failed");
      return res.json() as Promise<{ text: string }>;
    },
    onSuccess: (data) => {
      setTranscript(data.text);
      toast({ title: "Audio transcribed successfully" });
    },
    onError: () => {
      toast({ title: "Transcription failed", variant: "destructive" });
    },
  });
  
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      
      recorder.ondataavailable = (e) => chunks.push(e.data);
      recorder.onstop = () => {
        const blob = new Blob(chunks, { type: "audio/webm" });
        setAudioBlob(blob);
        stream.getTracks().forEach(track => track.stop());
      };
      
      recorder.start();
      setMediaRecorder(recorder);
      setIsRecording(true);
    } catch (err) {
      toast({ title: "Could not access microphone", variant: "destructive" });
    }
  };
  
  const stopRecording = () => {
    if (mediaRecorder) {
      mediaRecorder.stop();
      setIsRecording(false);
    }
  };
  
  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setAudioBlob(file);
    }
  };
  
  return (
    <div className="space-y-6">
      <div className="flex flex-col items-center gap-4 p-8 border-2 border-dashed rounded-lg">
        <div className="flex gap-4">
          <Button 
            size="lg"
            variant={isRecording ? "destructive" : "default"}
            onClick={isRecording ? stopRecording : startRecording}
            data-testid="button-record"
          >
            {isRecording ? <MicOff className="mr-2 h-5 w-5" /> : <Mic className="mr-2 h-5 w-5" />}
            {isRecording ? "Stop Recording" : "Start Recording"}
          </Button>
        </div>
        
        <div className="text-sm text-muted-foreground">or</div>
        
        <div>
          <Input 
            type="file" 
            accept="audio/*" 
            onChange={handleFileUpload}
            data-testid="input-audio-file"
          />
        </div>
        
        {audioBlob && (
          <div className="flex flex-col items-center gap-2">
            <audio src={URL.createObjectURL(audioBlob)} controls />
            <Button onClick={() => mutation.mutate(audioBlob)} disabled={mutation.isPending} data-testid="button-transcribe">
              {mutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Transcribe Audio
            </Button>
          </div>
        )}
      </div>
      
      {transcript && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-4">
            <CardTitle>Transcript</CardTitle>
            <CopyButton text={transcript} />
          </CardHeader>
          <CardContent>
            <div className="whitespace-pre-wrap">{transcript}</div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default function ClinicalToolsPage() {
  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-5xl p-6">
        <div className="mb-8">
          <h1 className="text-3xl font-bold">Clinical Documentation Tools</h1>
          <p className="text-muted-foreground mt-2">
            AI-powered tools for generating clinical documents, coding suggestions, and patient materials.
          </p>
        </div>
        
        <Tabs defaultValue="prior-auth" className="space-y-6">
          <TabsList className="grid w-full grid-cols-5">
            <TabsTrigger value="prior-auth" className="flex gap-2" data-testid="tab-prior-auth">
              <FileText className="h-4 w-4" />
              <span className="hidden md:inline">Prior Auth</span>
            </TabsTrigger>
            <TabsTrigger value="patient-instructions" className="flex gap-2" data-testid="tab-patient-instructions">
              <ClipboardList className="h-4 w-4" />
              <span className="hidden md:inline">Instructions</span>
            </TabsTrigger>
            <TabsTrigger value="icd10" className="flex gap-2" data-testid="tab-icd10">
              <Stethoscope className="h-4 w-4" />
              <span className="hidden md:inline">ICD-10</span>
            </TabsTrigger>
            <TabsTrigger value="discharge" className="flex gap-2" data-testid="tab-discharge">
              <FileOutput className="h-4 w-4" />
              <span className="hidden md:inline">Discharge</span>
            </TabsTrigger>
            <TabsTrigger value="voice" className="flex gap-2" data-testid="tab-voice">
              <Mic className="h-4 w-4" />
              <span className="hidden md:inline">Voice</span>
            </TabsTrigger>
          </TabsList>
          
          <TabsContent value="prior-auth">
            <Card>
              <CardHeader>
                <CardTitle>Prior Authorization Letter Generator</CardTitle>
                <CardDescription>
                  Generate professional prior authorization letters for insurance approval with medical coding.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <PriorAuthForm />
              </CardContent>
            </Card>
          </TabsContent>
          
          <TabsContent value="patient-instructions">
            <Card>
              <CardHeader>
                <CardTitle>Patient Instruction Sheets</CardTitle>
                <CardDescription>
                  Create patient-friendly care instructions in multiple languages at various reading levels.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <PatientInstructionsForm />
              </CardContent>
            </Card>
          </TabsContent>
          
          <TabsContent value="icd10">
            <Card>
              <CardHeader>
                <CardTitle>ICD-10 Coding Suggestions</CardTitle>
                <CardDescription>
                  Get ICD-10-CM diagnosis code suggestions from clinical notes with confidence levels.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ICD10CodesForm />
              </CardContent>
            </Card>
          </TabsContent>
          
          <TabsContent value="discharge">
            <Card>
              <CardHeader>
                <CardTitle>Discharge Summary Generator</CardTitle>
                <CardDescription>
                  Generate comprehensive hospital discharge summaries with diagnosis and procedure codes.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <DischargeSummaryForm />
              </CardContent>
            </Card>
          </TabsContent>
          
          <TabsContent value="voice">
            <Card>
              <CardHeader>
                <CardTitle>Voice Transcription</CardTitle>
                <CardDescription>
                  Record or upload audio for speech-to-text transcription of clinical notes.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <VoiceTranscriptionForm />
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
