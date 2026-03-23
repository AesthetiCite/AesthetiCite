import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ThumbsUp, ThumbsDown, Flag, X } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { getToken } from "@/lib/auth";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface AnswerFeedbackProps {
  queryId?: string;
  question: string;
}

export function AnswerFeedback({ queryId, question }: AnswerFeedbackProps) {
  const { toast } = useToast();
  const [rating, setRating] = useState<"positive" | "negative" | null>(null);
  const [showReport, setShowReport] = useState(false);
  const [reportText, setReportText] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const submitFeedback = async (type: "positive" | "negative") => {
    if (rating === type) return;
    setRating(type);
    
    try {
      const token = getToken();
      await fetch("/api/feedback", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token && { Authorization: `Bearer ${token}` }),
        },
        body: JSON.stringify({
          query_id: queryId,
          question,
          rating: type,
        }),
      });
      toast({ title: type === "positive" ? "Thanks for your feedback!" : "Sorry to hear that" });
    } catch {
      // Silent fail for feedback
    }
  };

  const submitReport = async () => {
    if (!reportText.trim()) return;
    setIsSubmitting(true);
    
    try {
      const token = getToken();
      await fetch("/api/feedback/report", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token && { Authorization: `Bearer ${token}` }),
        },
        body: JSON.stringify({
          query_id: queryId,
          question,
          report: reportText,
        }),
      });
      toast({ title: "Report submitted", description: "Thank you for helping us improve" });
      setShowReport(false);
      setReportText("");
    } catch {
      toast({ variant: "destructive", title: "Failed to submit report" });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex items-center gap-1">
      <span className="text-xs text-muted-foreground mr-1">Was this helpful?</span>
      <Button
        variant={rating === "positive" ? "default" : "ghost"}
        size="icon"
        className="h-7 w-7"
        onClick={() => submitFeedback("positive")}
        data-testid="button-feedback-positive"
      >
        <ThumbsUp className="h-3.5 w-3.5" />
      </Button>
      <Button
        variant={rating === "negative" ? "destructive" : "ghost"}
        size="icon"
        className="h-7 w-7"
        onClick={() => submitFeedback("negative")}
        data-testid="button-feedback-negative"
      >
        <ThumbsDown className="h-3.5 w-3.5" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="h-7 w-7"
        onClick={() => setShowReport(true)}
        title="Report an issue"
        data-testid="button-report-issue"
      >
        <Flag className="h-3.5 w-3.5" />
      </Button>

      <Dialog open={showReport} onOpenChange={setShowReport}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Report an Issue</DialogTitle>
            <DialogDescription>
              Help us improve by describing what was wrong with this answer.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <Textarea
              value={reportText}
              onChange={(e) => setReportText(e.target.value)}
              placeholder="Please describe the issue (e.g., inaccurate information, missing citations, outdated data...)"
              rows={4}
              data-testid="textarea-report"
            />
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowReport(false)}>
                Cancel
              </Button>
              <Button 
                onClick={submitReport} 
                disabled={!reportText.trim() || isSubmitting}
                data-testid="button-submit-report"
              >
                Submit Report
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
