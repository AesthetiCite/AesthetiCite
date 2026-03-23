import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Calculator, X, Activity, Scale, Pill, Beaker } from "lucide-react";
import { useDeviceType } from "@/hooks/use-mobile";

interface ClinicalToolsPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

type ToolType = "bmi" | "bsa" | "egfr" | "converter" | null;

export function ClinicalToolsPanel({ isOpen, onClose }: ClinicalToolsPanelProps) {
  const [activeTool, setActiveTool] = useState<ToolType>(null);
  const [results, setResults] = useState<{ [key: string]: string }>({});
  const { isMobileOrTablet } = useDeviceType();
  
  // BMI inputs
  const [weight, setWeight] = useState("");
  const [height, setHeight] = useState("");
  
  // eGFR inputs
  const [creatinine, setCreatinine] = useState("");
  const [age, setAge] = useState("");
  const [sex, setSex] = useState("male");
  
  // Converter inputs
  const [fromValue, setFromValue] = useState("");
  const [fromUnit, setFromUnit] = useState("mg");
  const [toUnit, setToUnit] = useState("g");

  const calculateBMI = () => {
    const w = parseFloat(weight);
    const h = parseFloat(height) / 100; // cm to m
    if (w > 0 && h > 0) {
      const bmi = w / (h * h);
      let category = "";
      if (bmi < 18.5) category = "Underweight";
      else if (bmi < 25) category = "Normal";
      else if (bmi < 30) category = "Overweight";
      else category = "Obese";
      setResults({ ...results, bmi: `${bmi.toFixed(1)} kg/m² (${category})` });
    }
  };

  const calculateBSA = () => {
    const w = parseFloat(weight);
    const h = parseFloat(height);
    if (w > 0 && h > 0) {
      // Mosteller formula
      const bsa = Math.sqrt((h * w) / 3600);
      setResults({ ...results, bsa: `${bsa.toFixed(2)} m²` });
    }
  };

  const calculateEGFR = () => {
    const scr = parseFloat(creatinine);
    const a = parseFloat(age);
    if (scr > 0 && a > 0) {
      // CKD-EPI 2021 (without race)
      const k = sex === "female" ? 0.7 : 0.9;
      const alpha = sex === "female" ? -0.241 : -0.302;
      const sexMultiplier = sex === "female" ? 1.012 : 1;
      
      const scrK = scr / k;
      const egfr = 142 * Math.pow(Math.min(scrK, 1), alpha) * Math.pow(Math.max(scrK, 1), -1.200) * Math.pow(0.9938, a) * sexMultiplier;
      
      let stage = "";
      if (egfr >= 90) stage = "Normal (G1)";
      else if (egfr >= 60) stage = "Mildly decreased (G2)";
      else if (egfr >= 45) stage = "Mild-moderate (G3a)";
      else if (egfr >= 30) stage = "Moderate-severe (G3b)";
      else if (egfr >= 15) stage = "Severely decreased (G4)";
      else stage = "Kidney failure (G5)";
      
      setResults({ ...results, egfr: `${egfr.toFixed(0)} mL/min/1.73m² - ${stage}` });
    }
  };

  const convertUnit = () => {
    const val = parseFloat(fromValue);
    if (val <= 0) return;
    
    const conversions: { [key: string]: number } = {
      mg: 0.001, g: 1, kg: 1000, mcg: 0.000001,
      ml: 0.001, L: 1, mL: 0.001,
    };
    
    const baseValue = val * (conversions[fromUnit] || 1);
    const result = baseValue / (conversions[toUnit] || 1);
    setResults({ ...results, converter: `${val} ${fromUnit} = ${result.toFixed(4)} ${toUnit}` });
  };

  if (!isOpen) return null;

  if (isMobileOrTablet) {
    return (
      <>
        <div 
          className="fixed inset-0 z-40 bg-black/30" 
          onClick={onClose}
          aria-hidden="true"
        />
        <div className="fixed inset-x-0 bottom-0 z-50">
          <Card className="shadow-lg relative rounded-t-2xl rounded-b-none">
            <div className="flex justify-center pt-2">
              <div className="w-12 h-1.5 bg-muted-foreground/30 rounded-full" />
            </div>
            <CardHeader className="pb-2 flex flex-row items-center justify-between gap-2 py-4">
              <CardTitle className="flex items-center gap-2 text-base">
                <Calculator className="h-5 w-5" />
                Clinical Tools
              </CardTitle>
              <Button variant="ghost" size="lg" onClick={onClose} data-testid="button-close-tools">
                <X className="h-5 w-5" />
              </Button>
            </CardHeader>
            <CardContent className="space-y-3 pb-6">
              <div className="grid grid-cols-4 gap-2">
                <Button
                  variant={activeTool === "bmi" ? "default" : "outline"}
                  size="lg"
                  onClick={() => setActiveTool(activeTool === "bmi" ? null : "bmi")}
                  className="text-sm"
                  data-testid="button-tool-bmi"
                >
                  <Scale className="h-4 w-4 mr-1.5" />
                  BMI
                </Button>
                <Button
                  variant={activeTool === "bsa" ? "default" : "outline"}
                  size="lg"
                  onClick={() => setActiveTool(activeTool === "bsa" ? null : "bsa")}
                  className="text-sm"
                  data-testid="button-tool-bsa"
                >
                  <Activity className="h-4 w-4 mr-1.5" />
                  BSA
                </Button>
                <Button
                  variant={activeTool === "egfr" ? "default" : "outline"}
                  size="lg"
                  onClick={() => setActiveTool(activeTool === "egfr" ? null : "egfr")}
                  className="text-sm"
                  data-testid="button-tool-egfr"
                >
                  <Beaker className="h-4 w-4 mr-1.5" />
                  eGFR
                </Button>
                <Button
                  variant={activeTool === "converter" ? "default" : "outline"}
                  size="lg"
                  onClick={() => setActiveTool(activeTool === "converter" ? null : "converter")}
                  className="text-sm"
                  data-testid="button-tool-converter"
                >
                  <Pill className="h-4 w-4 mr-1.5" />
                  Unit
                </Button>
              </div>

              {activeTool === "bmi" && (
                <div className="space-y-3 pt-3 border-t">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label className="text-sm">Weight (kg)</Label>
                      <Input type="number" inputMode="decimal" value={weight} onChange={(e) => setWeight(e.target.value)} placeholder="70" data-testid="input-weight" />
                    </div>
                    <div>
                      <Label className="text-sm">Height (cm)</Label>
                      <Input type="number" inputMode="decimal" value={height} onChange={(e) => setHeight(e.target.value)} placeholder="175" data-testid="input-height" />
                    </div>
                  </div>
                  <Button size="lg" className="w-full" onClick={calculateBMI} data-testid="button-calculate-bmi">Calculate BMI</Button>
                  {results.bmi && <div className="bg-muted p-3 rounded text-base" data-testid="result-bmi">{results.bmi}</div>}
                </div>
              )}

              {activeTool === "bsa" && (
                <div className="space-y-3 pt-3 border-t">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label className="text-sm">Weight (kg)</Label>
                      <Input type="number" inputMode="decimal" value={weight} onChange={(e) => setWeight(e.target.value)} placeholder="70" />
                    </div>
                    <div>
                      <Label className="text-sm">Height (cm)</Label>
                      <Input type="number" inputMode="decimal" value={height} onChange={(e) => setHeight(e.target.value)} placeholder="175" />
                    </div>
                  </div>
                  <Button size="lg" className="w-full" onClick={calculateBSA} data-testid="button-calculate-bsa">Calculate BSA</Button>
                  {results.bsa && <div className="bg-muted p-3 rounded text-base" data-testid="result-bsa">{results.bsa}</div>}
                </div>
              )}

              {activeTool === "egfr" && (
                <div className="space-y-3 pt-3 border-t">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label className="text-sm">Creatinine (mg/dL)</Label>
                      <Input type="number" inputMode="decimal" value={creatinine} onChange={(e) => setCreatinine(e.target.value)} placeholder="1.0" data-testid="input-creatinine" />
                    </div>
                    <div>
                      <Label className="text-sm">Age (years)</Label>
                      <Input type="number" inputMode="numeric" value={age} onChange={(e) => setAge(e.target.value)} placeholder="50" data-testid="input-age" />
                    </div>
                  </div>
                  <div>
                    <Label className="text-sm">Sex</Label>
                    <Select value={sex} onValueChange={setSex}>
                      <SelectTrigger data-testid="select-sex"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="male">Male</SelectItem>
                        <SelectItem value="female">Female</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <Button size="lg" className="w-full" onClick={calculateEGFR} data-testid="button-calculate-egfr">Calculate eGFR</Button>
                  {results.egfr && <div className="bg-muted p-3 rounded text-base" data-testid="result-egfr">{results.egfr}</div>}
                </div>
              )}

              {activeTool === "converter" && (
                <div className="space-y-3 pt-3 border-t">
                  <div className="grid grid-cols-3 gap-2">
                    <div>
                      <Label className="text-sm">Value</Label>
                      <Input type="number" inputMode="decimal" value={fromValue} onChange={(e) => setFromValue(e.target.value)} placeholder="100" data-testid="input-convert-value" />
                    </div>
                    <div>
                      <Label className="text-sm">From</Label>
                      <Select value={fromUnit} onValueChange={setFromUnit}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="mg">mg</SelectItem>
                          <SelectItem value="g">g</SelectItem>
                          <SelectItem value="kg">kg</SelectItem>
                          <SelectItem value="mcg">mcg</SelectItem>
                          <SelectItem value="mL">mL</SelectItem>
                          <SelectItem value="L">L</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="text-sm">To</Label>
                      <Select value={toUnit} onValueChange={setToUnit}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="mg">mg</SelectItem>
                          <SelectItem value="g">g</SelectItem>
                          <SelectItem value="kg">kg</SelectItem>
                          <SelectItem value="mcg">mcg</SelectItem>
                          <SelectItem value="mL">mL</SelectItem>
                          <SelectItem value="L">L</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <Button size="lg" className="w-full" onClick={convertUnit} data-testid="button-convert">Convert</Button>
                  {results.converter && <div className="bg-muted p-3 rounded text-base" data-testid="result-converter">{results.converter}</div>}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </>
    );
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 w-80">
      <Card className="shadow-lg relative">
          <CardHeader className="pb-2 flex flex-row items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Calculator className="h-4 w-4" />
            Clinical Tools
          </CardTitle>
          <Button variant="ghost" size="icon" onClick={onClose} data-testid="button-close-tools">
            <X className="h-4 w-4" />
          </Button>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="grid grid-cols-4 gap-1">
            <Button
              variant={activeTool === "bmi" ? "default" : "outline"}
              size="sm"
              onClick={() => setActiveTool(activeTool === "bmi" ? null : "bmi")}
              className="text-xs px-2"
              data-testid="button-tool-bmi"
            >
              <Scale className="h-3 w-3 mr-1" />
              BMI
            </Button>
            <Button
              variant={activeTool === "bsa" ? "default" : "outline"}
              size="sm"
              onClick={() => setActiveTool(activeTool === "bsa" ? null : "bsa")}
              className="text-xs px-2"
              data-testid="button-tool-bsa"
            >
              <Activity className="h-3 w-3 mr-1" />
              BSA
            </Button>
            <Button
              variant={activeTool === "egfr" ? "default" : "outline"}
              size="sm"
              onClick={() => setActiveTool(activeTool === "egfr" ? null : "egfr")}
              className="text-xs px-2"
              data-testid="button-tool-egfr"
            >
              <Beaker className="h-3 w-3 mr-1" />
              eGFR
            </Button>
            <Button
              variant={activeTool === "converter" ? "default" : "outline"}
              size="sm"
              onClick={() => setActiveTool(activeTool === "converter" ? null : "converter")}
              className="text-xs px-2"
              data-testid="button-tool-converter"
            >
              <Pill className="h-3 w-3 mr-1" />
              Unit
            </Button>
          </div>

          {activeTool === "bmi" && (
            <div className="space-y-2 pt-2 border-t">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label className="text-xs">Weight (kg)</Label>
                  <Input type="number" inputMode="decimal" value={weight} onChange={(e) => setWeight(e.target.value)} placeholder="70" data-testid="input-weight" />
                </div>
                <div>
                  <Label className="text-xs">Height (cm)</Label>
                  <Input type="number" inputMode="decimal" value={height} onChange={(e) => setHeight(e.target.value)} placeholder="175" data-testid="input-height" />
                </div>
              </div>
              <Button size="sm" className="w-full" onClick={calculateBMI} data-testid="button-calculate-bmi">Calculate BMI</Button>
              {results.bmi && <div className="bg-muted p-2 rounded text-sm" data-testid="result-bmi">{results.bmi}</div>}
            </div>
          )}

          {activeTool === "bsa" && (
            <div className="space-y-2 pt-2 border-t">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label className="text-xs">Weight (kg)</Label>
                  <Input type="number" inputMode="decimal" value={weight} onChange={(e) => setWeight(e.target.value)} placeholder="70" />
                </div>
                <div>
                  <Label className="text-xs">Height (cm)</Label>
                  <Input type="number" inputMode="decimal" value={height} onChange={(e) => setHeight(e.target.value)} placeholder="175" />
                </div>
              </div>
              <Button size="sm" className="w-full" onClick={calculateBSA} data-testid="button-calculate-bsa">Calculate BSA</Button>
              {results.bsa && <div className="bg-muted p-2 rounded text-sm" data-testid="result-bsa">{results.bsa}</div>}
            </div>
          )}

          {activeTool === "egfr" && (
            <div className="space-y-2 pt-2 border-t">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label className="text-xs">Creatinine (mg/dL)</Label>
                  <Input type="number" inputMode="decimal" value={creatinine} onChange={(e) => setCreatinine(e.target.value)} placeholder="1.0" data-testid="input-creatinine" />
                </div>
                <div>
                  <Label className="text-xs">Age (years)</Label>
                  <Input type="number" inputMode="numeric" value={age} onChange={(e) => setAge(e.target.value)} placeholder="50" data-testid="input-age" />
                </div>
              </div>
              <div>
                <Label className="text-xs">Sex</Label>
                <Select value={sex} onValueChange={setSex}>
                  <SelectTrigger data-testid="select-sex"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="male">Male</SelectItem>
                    <SelectItem value="female">Female</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button size="sm" className="w-full" onClick={calculateEGFR} data-testid="button-calculate-egfr">Calculate eGFR (CKD-EPI)</Button>
              {results.egfr && <div className="bg-muted p-2 rounded text-sm" data-testid="result-egfr">{results.egfr}</div>}
            </div>
          )}

          {activeTool === "converter" && (
            <div className="space-y-2 pt-2 border-t">
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <Label className="text-xs">Value</Label>
                  <Input type="number" inputMode="decimal" value={fromValue} onChange={(e) => setFromValue(e.target.value)} placeholder="100" data-testid="input-convert-value" />
                </div>
                <div>
                  <Label className="text-xs">From</Label>
                  <Select value={fromUnit} onValueChange={setFromUnit}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="mg">mg</SelectItem>
                      <SelectItem value="g">g</SelectItem>
                      <SelectItem value="kg">kg</SelectItem>
                      <SelectItem value="mcg">mcg</SelectItem>
                      <SelectItem value="mL">mL</SelectItem>
                      <SelectItem value="L">L</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">To</Label>
                  <Select value={toUnit} onValueChange={setToUnit}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="mg">mg</SelectItem>
                      <SelectItem value="g">g</SelectItem>
                      <SelectItem value="kg">kg</SelectItem>
                      <SelectItem value="mcg">mcg</SelectItem>
                      <SelectItem value="mL">mL</SelectItem>
                      <SelectItem value="L">L</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <Button size="sm" className="w-full" onClick={convertUnit} data-testid="button-convert">Convert</Button>
              {results.converter && <div className="bg-muted p-2 rounded text-sm" data-testid="result-converter">{results.converter}</div>}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export function ClinicalToolsTrigger({ onClick }: { onClick: () => void }) {
  return (
    <div className="fixed bottom-6 right-5 z-40 flex flex-col items-end gap-1.5">
      <div className="text-[10px] text-muted-foreground bg-background/80 backdrop-blur rounded px-2 py-0.5 border shadow-sm whitespace-nowrap">
        BMI · BSA · eGFR · Unit Converter
      </div>
      <Button
        onClick={onClick}
        className="flex items-center gap-2 h-11 px-4 rounded-full shadow-lg"
        data-testid="button-open-clinical-tools"
      >
        <Calculator className="h-4 w-4" />
        <span className="text-sm font-medium">Clinical Tools</span>
      </Button>
    </div>
  );
}
