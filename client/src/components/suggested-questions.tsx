import { Lightbulb } from "lucide-react";

interface SuggestedQuestionsProps {
  onSelect: (question: string) => void;
}

const SUGGESTED_QUESTIONS = [
  "What are the latest treatments for type 2 diabetes?",
  "How effective is cognitive behavioral therapy for anxiety?",
  "What is the evidence for intermittent fasting benefits?",
  "What are the risk factors for cardiovascular disease?",
  "How does sleep affect cognitive performance?",
  "What is the current research on Alzheimer's prevention?",
];

export function SuggestedQuestions({ onSelect }: SuggestedQuestionsProps) {
  return (
    <div className="w-full max-w-3xl mx-auto mt-8">
      <div className="flex items-center gap-2 mb-4 text-muted-foreground">
        <Lightbulb className="w-4 h-4" />
        <span className="text-sm font-medium">Suggested questions</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {SUGGESTED_QUESTIONS.map((question, index) => (
          <button
            key={index}
            onClick={() => onSelect(question)}
            data-testid={`button-suggestion-${index}`}
            className="text-left p-4 rounded-lg border bg-card hover-elevate active-elevate-2 transition-colors cursor-pointer"
          >
            <span className="text-sm text-foreground leading-relaxed">
              {question}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
