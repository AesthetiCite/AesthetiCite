import { useState, useEffect } from "react";
import { Link, useSearch } from "wouter";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Loader2, CheckCircle2, AlertCircle, ArrowLeft } from "lucide-react";
import { setPasswordWithToken } from "@/lib/auth";
import { useToast } from "@/hooks/use-toast";
import { ThemeToggle } from "@/components/theme-toggle";
import { LanguageSelector } from "@/components/language-selector";

export default function SetPasswordPage() {
  const search = useSearch();
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    const params = new URLSearchParams(search);
    const tokenParam = params.get("token");
    if (tokenParam) {
      setToken(tokenParam);
    }
  }, [search]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    if (password !== confirmPassword) {
      toast({
        variant: "destructive",
        title: "Passwords don't match",
        description: "Please make sure both passwords are the same.",
      });
      return;
    }

    if (password.length < 8) {
      toast({
        variant: "destructive",
        title: "Password too short",
        description: "Password must be at least 8 characters.",
      });
      return;
    }

    setIsLoading(true);

    try {
      const result = await setPasswordWithToken(token, password);
      setSuccess(true);
      toast({
        title: "Password set",
        description: result.message || "You can now log in.",
      });
    } catch (err) {
      toast({
        variant: "destructive",
        title: "Failed to set password",
        description: err instanceof Error ? err.message : "Please try again",
      });
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-muted/30 flex items-center justify-center p-6">
      <div className="absolute top-4 right-4 flex items-center gap-2">
        <LanguageSelector />
        <ThemeToggle />
      </div>

      <div className="w-full max-w-md">
        <div className="flex flex-col items-center mb-8">
          <img
            src="/aestheticite-logo.png"
            alt="AesthetiCite"
            className="w-20 h-20 object-contain drop-shadow-lg"
            data-testid="img-setpw-logo"
          />
        </div>

        <div className="text-center mb-6">
          <h2
            className="text-2xl font-bold tracking-tight"
            data-testid="text-setpw-title"
          >
            Set your password
          </h2>
          <p className="text-muted-foreground text-sm mt-1">
            Use the secure link sent to your email. This link expires after a
            short time.
          </p>
        </div>

        <Card className="border-0 shadow-xl bg-card/80 backdrop-blur">
          <CardContent className="p-6">
            {!token ? (
              <div className="text-center py-4">
                <AlertCircle className="w-12 h-12 text-amber-500 mx-auto mb-4" />
                <h3 className="font-semibold text-lg mb-2">Invalid link</h3>
                <p className="text-muted-foreground text-sm mb-4">
                  This link is missing or invalid. Please use the link from your
                  email.
                </p>
                <Link href="/request-access">
                  <Button variant="outline" data-testid="button-request-new">
                    Request new link
                  </Button>
                </Link>
              </div>
            ) : success ? (
              <div className="text-center py-4">
                <CheckCircle2 className="w-12 h-12 text-green-500 mx-auto mb-4" />
                <h3 className="font-semibold text-lg mb-2">Password set!</h3>
                <p className="text-muted-foreground text-sm mb-4">
                  Your password has been set. You can now log in to AesthetiCite.
                </p>
                <Link href="/login">
                  <Button data-testid="button-go-to-login">Go to login</Button>
                </Link>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="password" className="text-sm font-medium">
                    New password
                  </Label>
                  <Input
                    id="password"
                    type="password"
                    placeholder="Minimum 8 characters"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    minLength={8}
                    className="bg-muted/50 border-0"
                    data-testid="input-password"
                  />
                </div>
                <div className="space-y-2">
                  <Label
                    htmlFor="confirmPassword"
                    className="text-sm font-medium"
                  >
                    Confirm password
                  </Label>
                  <Input
                    id="confirmPassword"
                    type="password"
                    placeholder="Repeat your password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    required
                    minLength={8}
                    className="bg-muted/50 border-0"
                    data-testid="input-confirm-password"
                  />
                </div>
                <Button
                  type="submit"
                  className="w-full shadow-lg shadow-primary/25"
                  disabled={isLoading}
                  data-testid="button-submit"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    "Set password"
                  )}
                </Button>
              </form>
            )}
          </CardContent>
        </Card>

        <div className="text-center mt-6">
          <Link href="/login">
            <Button variant="ghost" size="sm" data-testid="link-login">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Go to login
            </Button>
          </Link>
        </div>
      </div>
    </div>
  );
}
