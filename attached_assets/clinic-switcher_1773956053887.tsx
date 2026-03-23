import { Building2, ChevronDown, CheckCircle2 } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useClinicContext, type ClinicMembership } from "@/hooks/use-clinic-context";

const ROLE_COLORS: Record<string, string> = {
  super_admin:  "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300",
  org_admin:    "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300",
  clinic_admin: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  clinician:    "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  reviewer:     "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
};

function roleBadgeClass(role: string): string {
  return ROLE_COLORS[role] ?? "bg-muted text-muted-foreground";
}

function formatRole(role: string): string {
  return role.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function ClinicSwitcher() {
  const { memberships, selectedClinic, selectClinic, isLoading } = useClinicContext();

  if (isLoading) {
    return <Skeleton className="h-8 w-48 rounded-md" />;
  }

  if (!selectedClinic) return null;

  // Group by org
  const grouped: Record<string, { org_name: string; clinics: ClinicMembership[] }> = {};
  for (const m of memberships) {
    if (!grouped[m.org_id]) {
      grouped[m.org_id] = { org_name: m.org_name, clinics: [] };
    }
    grouped[m.org_id].clinics.push(m);
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="flex items-center gap-2 h-9 max-w-xs"
          data-testid="clinic-switcher-trigger"
        >
          <Building2 className="h-4 w-4 text-muted-foreground flex-shrink-0" />
          <span className="truncate text-sm font-medium">
            {selectedClinic.clinic_name}
          </span>
          <Badge
            className={`text-xs px-1.5 py-0 flex-shrink-0 ${roleBadgeClass(selectedClinic.role)}`}
            variant="outline"
          >
            {formatRole(selectedClinic.role)}
          </Badge>
          {memberships.length > 1 && (
            <ChevronDown className="h-3 w-3 text-muted-foreground flex-shrink-0" />
          )}
        </Button>
      </DropdownMenuTrigger>

      {memberships.length > 1 && (
        <DropdownMenuContent align="start" className="w-72">
          {Object.entries(grouped).map(([orgId, group]) => (
            <div key={orgId}>
              <DropdownMenuLabel className="text-xs text-muted-foreground font-normal">
                {group.org_name}
              </DropdownMenuLabel>
              {group.clinics.map((m) => (
                <DropdownMenuItem
                  key={m.clinic_id}
                  onClick={() => selectClinic(m)}
                  className="flex items-center justify-between gap-2 cursor-pointer"
                  data-testid={`clinic-option-${m.clinic_id}`}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <Building2 className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                    <span className="truncate text-sm">{m.clinic_name}</span>
                  </div>
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    <Badge
                      className={`text-xs px-1.5 py-0 ${roleBadgeClass(m.role)}`}
                      variant="outline"
                    >
                      {formatRole(m.role)}
                    </Badge>
                    {selectedClinic.clinic_id === m.clinic_id && (
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                    )}
                  </div>
                </DropdownMenuItem>
              ))}
              <DropdownMenuSeparator />
            </div>
          ))}
        </DropdownMenuContent>
      )}
    </DropdownMenu>
  );
}
