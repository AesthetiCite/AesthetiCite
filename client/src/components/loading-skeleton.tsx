import { Card } from "@/components/ui/card";

function ShimmerBar({ className }: { className?: string }) {
  return <div className={`rounded-md bg-muted skeleton-shimmer ${className || ""}`} />;
}

export function LoadingSkeleton() {
  return (
    <div className="w-full max-w-4xl mx-auto space-y-6 animate-float-in" data-testid="loading-skeleton">
      <Card className="p-6 md:p-8 space-y-4">
        <div className="flex items-center gap-3 mb-2">
          <ShimmerBar className="h-6 w-6 rounded-full" />
          <ShimmerBar className="h-4 w-32" />
        </div>
        <div className="space-y-3">
          <ShimmerBar className="h-4 w-full" />
          <ShimmerBar className="h-4 w-[95%]" />
          <ShimmerBar className="h-4 w-[88%]" />
        </div>
        <div className="space-y-3 pt-2">
          <ShimmerBar className="h-4 w-full" />
          <ShimmerBar className="h-4 w-[92%]" />
          <ShimmerBar className="h-4 w-[85%]" />
          <ShimmerBar className="h-4 w-[78%]" />
        </div>
        <div className="space-y-3 pt-2">
          <ShimmerBar className="h-4 w-full" />
          <ShimmerBar className="h-4 w-[90%]" />
          <ShimmerBar className="h-4 w-[75%]" />
        </div>
      </Card>

      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <ShimmerBar className="h-5 w-5 rounded-full" />
          <ShimmerBar className="h-4 w-24" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i} className="p-4">
              <div className="flex items-start gap-3">
                <ShimmerBar className="h-6 w-6 rounded-full shrink-0" />
                <div className="flex-1 space-y-2">
                  <ShimmerBar className="h-3.5 w-full" />
                  <ShimmerBar className="h-3.5 w-3/4" />
                  <ShimmerBar className="h-3 w-1/2" />
                </div>
              </div>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
