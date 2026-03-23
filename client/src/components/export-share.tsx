import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { Download, Copy, Share2, FileText, Check, Link } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

interface Citation {
  id?: number;
  title: string;
  source?: string;
  url?: string;
  year?: number;
  authors?: string;
}

interface ExportShareProps {
  question: string;
  answer: string;
  citations: Citation[];
  clinicalSummary?: string;
  aciScore?: number | null;
  evidenceBadge?: string | null;
}

export function ExportShare({ question, answer, citations, clinicalSummary, aciScore, evidenceBadge }: ExportShareProps) {
  const { toast } = useToast();
  const [copied, setCopied] = useState(false);

  const formatForCopy = () => {
    let text = `Question: ${question}\n\n`;
    if (clinicalSummary) {
      text += `Clinical Summary: ${clinicalSummary}\n\n`;
    }
    text += `Answer:\n${answer}\n\n`;
    text += `References:\n`;
    citations.forEach((c, i) => {
      text += `[${i + 1}] ${c.title}`;
      if (c.source) text += ` - ${c.source}`;
      if (c.year) text += ` (${c.year})`;
      if (c.url) text += `\n    ${c.url}`;
      text += "\n";
    });
    return text;
  };

  const handleCopyText = async () => {
    try {
      await navigator.clipboard.writeText(formatForCopy());
      setCopied(true);
      toast({ title: "Copied to clipboard", description: "Answer copied with citations" });
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast({ variant: "destructive", title: "Copy failed" });
    }
  };

  const handleCopyLink = async () => {
    try {
      const params = new URLSearchParams({ q: question });
      const url = `${window.location.origin}/ask?${params.toString()}`;
      await navigator.clipboard.writeText(url);
      toast({ title: "Link copied", description: "Share link copied to clipboard" });
    } catch {
      toast({ variant: "destructive", title: "Copy failed" });
    }
  };

  const handleDownloadPDF = async () => {
    try {
      const response = await fetch("/api/export/pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, answer, citations, clinicalSummary, aciScore: aciScore ?? undefined, evidenceBadge: evidenceBadge ?? undefined }),
      });
      
      if (!response.ok) throw new Error("Export failed");
      
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `aestheticite-answer-${Date.now()}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      
      toast({ title: "Downloaded", description: "PDF saved successfully" });
    } catch {
      toast({ variant: "destructive", title: "Export failed", description: "Could not generate PDF" });
    }
  };

  const handleDownloadText = () => {
    const text = formatForCopy();
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `aestheticite-answer-${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    toast({ title: "Downloaded", description: "Text file saved" });
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" data-testid="button-export-share">
          <Share2 className="h-4 w-4 mr-2" />
          Export
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={handleCopyText} data-testid="menu-copy-text">
          {copied ? <Check className="h-4 w-4 mr-2" /> : <Copy className="h-4 w-4 mr-2" />}
          Copy as text
        </DropdownMenuItem>
        <DropdownMenuItem onClick={handleCopyLink} data-testid="menu-copy-link">
          <Link className="h-4 w-4 mr-2" />
          Copy share link
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={handleDownloadText} data-testid="menu-download-txt">
          <FileText className="h-4 w-4 mr-2" />
          Download as .txt
        </DropdownMenuItem>
        <DropdownMenuItem onClick={handleDownloadPDF} data-testid="menu-download-pdf">
          <Download className="h-4 w-4 mr-2" />
          Download Report
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
