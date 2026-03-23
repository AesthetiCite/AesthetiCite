import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getToken } from "@/lib/auth";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ClinicMembership {
  id: string;
  clinic_id: string;
  clinic_name: string;
  org_id: string;
  org_name: string;
  role: "super_admin" | "org_admin" | "clinic_admin" | "clinician" | "reviewer";
}

export interface ClinicContext {
  memberships: ClinicMembership[];
  selectedClinic: ClinicMembership | null;
  selectClinic: (membership: ClinicMembership) => void;
  isLoading: boolean;
  role: string | null;
  canAdmin: boolean;
  isReady: boolean;
}

const ClinicCtx = createContext<ClinicContext | null>(null);

// ---------------------------------------------------------------------------
// Storage key
// ---------------------------------------------------------------------------

const STORAGE_KEY = "aestheticite_selected_clinic";

function loadSaved(): ClinicMembership | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as ClinicMembership) : null;
  } catch {
    return null;
  }
}

function saveToDisk(m: ClinicMembership): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(m));
  } catch {}
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

async function fetchMyClinics(): Promise<ClinicMembership[]> {
  const token = getToken();
  const res = await fetch("/api/workspace/clinics/me", {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) return [];
  return res.json();
}

async function postSelectClinic(clinic_id: string): Promise<void> {
  const token = getToken();
  await fetch("/api/workspace/clinics/select", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ clinic_id }),
  });
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function ClinicProvider({ children }: { children: ReactNode }) {
  const [selected, setSelected] = useState<ClinicMembership | null>(loadSaved);

  const { data: memberships = [], isLoading } = useQuery({
    queryKey: ["clinics-me"],
    queryFn: fetchMyClinics,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  // Auto-select first clinic if nothing saved or saved clinic no longer in memberships
  useEffect(() => {
    if (memberships.length === 0) return;
    if (selected && memberships.some((m) => m.clinic_id === selected.clinic_id)) return;
    const first = memberships[0];
    setSelected(first);
    saveToDisk(first);
  }, [memberships]);

  const selectClinic = (membership: ClinicMembership) => {
    setSelected(membership);
    saveToDisk(membership);
    postSelectClinic(membership.clinic_id).catch(() => {});
  };

  const role = selected?.role ?? null;
  const adminRoles = ["super_admin", "org_admin", "clinic_admin"];
  const canAdmin = role !== null && adminRoles.includes(role);

  return (
    <ClinicCtx.Provider
      value={{
        memberships,
        selectedClinic: selected,
        selectClinic,
        isLoading,
        role,
        canAdmin,
        isReady: !isLoading && selected !== null,
      }}
    >
      {children}
    </ClinicCtx.Provider>
  );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useClinicContext(): ClinicContext {
  const ctx = useContext(ClinicCtx);
  if (!ctx) throw new Error("useClinicContext must be used within <ClinicProvider>");
  return ctx;
}
