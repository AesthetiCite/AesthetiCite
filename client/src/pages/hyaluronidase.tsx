import { useLocation } from "wouter";
import { ArrowLeft, Syringe } from "lucide-react";
import { Button } from "@/components/ui/button";
import { HyaluronidaseCalc } from "@/components/hyaluronidase-calc";

export default function HyaluronidaseCalcPage() {
  const [, setLocation] = useLocation();

  return (
    <div className="min-h-screen bg-background">
      <div className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur">
        <div className="max-w-2xl mx-auto px-4 sm:px-6 h-14 flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => setLocation("/")} className="gap-2 -ml-2">
            <ArrowLeft className="w-4 h-4" />
            <span className="hidden sm:inline">Back</span>
          </Button>
          <div className="w-px h-5 bg-border" />
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-red-500/10 flex items-center justify-center">
              <Syringe className="w-4 h-4 text-red-500" />
            </div>
            <span className="font-semibold text-sm">Hyaluronidase Calculator</span>
          </div>
        </div>
      </div>

      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-6">
        <HyaluronidaseCalc />
      </div>
    </div>
  );
}
