import { Link } from "wouter";
import { BRAND } from "../config";
import { ThemeToggle } from "./theme-toggle";
import { Button } from "./ui/button";
import { Shield } from "lucide-react";

type HeaderProps = {
  isAuthenticated?: boolean;
  minimal?: boolean;
  onHomeClick?: () => void;
};

export function Header({ isAuthenticated = false, minimal = false, onHomeClick }: HeaderProps) {
  const handleHomeClick = () => {
    if (onHomeClick) {
      onHomeClick();
    }
  };

  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60" data-testid="header">
      <div className="container mx-auto flex h-14 items-center justify-between gap-4 px-4">
        <Link href="/" data-testid="link-home" onClick={handleHomeClick}>
          <div className="flex items-baseline gap-3 cursor-pointer">
            <div className="text-xl font-semibold tracking-tight">
              {BRAND.name}
            </div>
            {!isAuthenticated && (
              <div className="text-sm text-muted-foreground">
                {BRAND.publicationsLabel}
              </div>
            )}
          </div>
        </Link>
        
        <div className="flex items-center gap-2" data-testid="header-actions">
          <ThemeToggle />
          {isAuthenticated ? (
            <nav className="flex items-center gap-2">
              <Link href="/network-safety-workspace">
                <Button variant="outline" size="sm" className="gap-1.5" data-testid="link-network-workspace">
                  <Shield className="h-3.5 w-3.5 text-red-500" />
                  <span className="hidden sm:inline">Network Workspace</span>
                  <span className="sm:hidden">Workspace</span>
                </Button>
              </Link>
            </nav>
          ) : !minimal ? (
            <nav className="flex items-center gap-2">
              <Link href="/tools">
                <Button variant="outline" size="sm" data-testid="link-tools">
                  Tools
                </Button>
              </Link>
              <Link href="/login">
                <Button size="sm" data-testid="link-login">
                  Login
                </Button>
              </Link>
            </nav>
          ) : null}
        </div>
      </div>
    </header>
  );
}

export default Header;
