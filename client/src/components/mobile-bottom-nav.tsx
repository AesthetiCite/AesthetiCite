import { Home, Search, Calculator, Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useDeviceType } from "@/hooks/use-mobile";

interface MobileBottomNavProps {
  onHomeClick: () => void;
  onSearchClick: () => void;
  onToolsClick: () => void;
  onFavoritesClick: () => void;
  activeTab?: "home" | "search" | "tools" | "favorites";
}

export function MobileBottomNav({
  onHomeClick,
  onSearchClick,
  onToolsClick,
  onFavoritesClick,
  activeTab = "home",
}: MobileBottomNavProps) {
  const { isMobileOrTablet } = useDeviceType();

  if (!isMobileOrTablet) return null;

  const navItems = [
    { id: "home", icon: Home, label: "Home", onClick: onHomeClick },
    { id: "search", icon: Search, label: "Search", onClick: onSearchClick },
    { id: "tools", icon: Calculator, label: "Tools", onClick: onToolsClick },
    { id: "favorites", icon: Star, label: "Saved", onClick: onFavoritesClick },
  ];

  return (
    <nav className="mobile-bottom-nav glass-panel" data-testid="nav-mobile-bottom">
      <div className="flex items-center justify-around px-2 py-2">
        {navItems.map((item) => (
          <Button
            key={item.id}
            variant={activeTab === item.id ? "secondary" : "ghost"}
            size="lg"
            onClick={item.onClick}
            className="flex flex-col gap-1"
            data-testid={`button-nav-${item.id}`}
          >
            <item.icon className="h-5 w-5" />
            <span className="text-xs font-medium">{item.label}</span>
          </Button>
        ))}
      </div>
    </nav>
  );
}
