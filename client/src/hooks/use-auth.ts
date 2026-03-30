import { useState, useEffect } from "react";
import { getToken, getMe } from "@/lib/auth";
import { useLocation } from "wouter";

interface AuthUser {
  id: string;
  email: string;
  full_name?: string;
  role?: string;
}

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  loading: boolean;
}

export function useAuth(): AuthState {
  const [state, setState] = useState<AuthState>({ token: null, user: null, loading: true });
  const [, navigate] = useLocation();

  useEffect(() => {
    const token = getToken();
    if (!token) {
      navigate("/login");
      setState({ token: null, user: null, loading: false });
      return;
    }
    getMe(token)
      .then((user) => setState({ token, user, loading: false }))
      .catch(() => {
        navigate("/login");
        setState({ token: null, user: null, loading: false });
      });
  }, []);

  return state;
}
