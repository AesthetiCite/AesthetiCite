import { Link } from "wouter";
import { Button } from "@/components/ui/button";
import { Search, ArrowLeft } from "lucide-react";

export default function NotFound() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-muted/30 flex items-center justify-center p-6">
      <div className="max-w-md w-full text-center">
        <div className="flex flex-col items-center mb-6">
          <img
            src="/aestheticite-logo.png"
            alt="AesthetiCite"
            className="w-16 h-16 object-contain mb-4"
            data-testid="img-404-logo"
          />
          <div className="text-7xl font-bold tracking-tight text-primary/20 mb-2" data-testid="text-404">404</div>
          <h1 className="text-2xl font-bold tracking-tight" data-testid="text-404-title">Page not found</h1>
          <p className="mt-2 text-muted-foreground leading-relaxed" data-testid="text-404-desc">
            The page you're looking for doesn't exist or may have been moved.
          </p>
        </div>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mt-8">
          <Link href="/">
            <Button data-testid="button-go-home">
              <Search className="w-4 h-4 mr-2" />
              Go to Search
            </Button>
          </Link>
          <Link href="/welcome">
            <Button variant="outline" data-testid="button-go-landing">
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back to Home
            </Button>
          </Link>
        </div>
      </div>
    </div>
  );
}
