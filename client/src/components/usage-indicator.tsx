import { useState, useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { Activity } from "lucide-react";

const USAGE_KEY = "aestheticite_usage";
const RATE_LIMIT = 60;
const WINDOW_MS = 60 * 1000;

interface UsageData {
  timestamps: number[];
}

function getUsage(): UsageData {
  try {
    const raw = localStorage.getItem(USAGE_KEY);
    return raw ? JSON.parse(raw) : { timestamps: [] };
  } catch {
    return { timestamps: [] };
  }
}

function cleanOld(data: UsageData): UsageData {
  const cutoff = Date.now() - WINDOW_MS;
  return { timestamps: data.timestamps.filter((t) => t > cutoff) };
}

export function recordQuery() {
  const data = cleanOld(getUsage());
  data.timestamps.push(Date.now());
  localStorage.setItem(USAGE_KEY, JSON.stringify(data));
}

export function UsageIndicator() {
  const [count, setCount] = useState(0);

  useEffect(() => {
    function update() {
      const data = cleanOld(getUsage());
      setCount(data.timestamps.length);
    }
    update();
    const interval = setInterval(update, 5000);
    return () => clearInterval(interval);
  }, []);

  const remaining = Math.max(0, RATE_LIMIT - count);
  const pct = Math.round((count / RATE_LIMIT) * 100);
  const isLow = remaining <= 10;
  const isCritical = remaining <= 3;

  return (
    <Badge
      variant="secondary"
      className={`text-[10px] gap-1 ${isCritical ? "text-red-600 dark:text-red-400" : isLow ? "text-amber-600 dark:text-amber-400" : ""}`}
      data-testid="badge-usage-indicator"
    >
      <Activity className="w-3 h-3" />
      {remaining}/{RATE_LIMIT}
      <span className="hidden sm:inline">queries left</span>
    </Badge>
  );
}
