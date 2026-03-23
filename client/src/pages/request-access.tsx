import { useState } from "react";
import { Link } from "wouter";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Loader2, CheckCircle2, ArrowLeft, Stethoscope, GraduationCap } from "lucide-react";
import { requestAccess, UserRole } from "@/lib/auth";
import { useToast } from "@/hooks/use-toast";
import { ThemeToggle } from "@/components/theme-toggle";
import { LanguageSelector } from "@/components/language-selector";
import { useLocale } from "@/hooks/use-locale";

export default function RequestAccessPage() {
  const [role, setRole] = useState<UserRole>("clinician");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [practitionerId, setPractitionerId] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const { toast } = useToast();
  const { t } = useLocale();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setIsLoading(true);

    try {
      const result = await requestAccess(fullName, email, practitionerId, role);
      setSuccess(true);
      toast({
        title: t('requestAccess.sent'),
        description: result.message || t('requestAccess.checkEmail'),
      });
    } catch (err) {
      toast({
        variant: "destructive",
        title: t('requestAccess.failed'),
        description: err instanceof Error ? err.message : t('requestAccess.tryAgain'),
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
            className="h-20 object-contain"
          />
        </div>

        <div className="text-center mb-6">
          <h2
            className="text-2xl font-bold tracking-tight"
            data-testid="text-request-title"
          >
            {t('requestAccess.title')}
          </h2>
          <p className="text-muted-foreground text-sm mt-1">
            {t('requestAccess.subtitle')}
          </p>
        </div>

        <Card className="border-0 shadow-xl bg-card/80 backdrop-blur">
          <CardContent className="p-6">
            {success ? (
              <div className="text-center py-4">
                <CheckCircle2 className="w-12 h-12 text-green-500 mx-auto mb-4" />
                <h3 className="font-semibold text-lg mb-2">{t('requestAccess.checkEmail')}</h3>
                <p className="text-muted-foreground text-sm mb-4">
                  {t('requestAccess.emailSent')}
                </p>
                <Link href="/login">
                  <Button variant="outline" data-testid="button-go-to-login">
                    {t('requestAccess.goToLogin')}
                  </Button>
                </Link>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-2">
                  <Label className="text-sm font-medium">{t('requestAccess.role')}</Label>
                  <div className="grid grid-cols-2 gap-2">
                    <Button
                      type="button"
                      variant={role === "clinician" ? "default" : "outline"}
                      className="h-auto py-3 flex flex-col items-center gap-1"
                      onClick={() => setRole("clinician")}
                      data-testid="button-role-clinician"
                    >
                      <Stethoscope className="w-5 h-5" />
                      <span className="text-sm font-medium">{t('requestAccess.roleClinician')}</span>
                    </Button>
                    <Button
                      type="button"
                      variant={role === "student" ? "default" : "outline"}
                      className="h-auto py-3 flex flex-col items-center gap-1"
                      onClick={() => setRole("student")}
                      data-testid="button-role-student"
                    >
                      <GraduationCap className="w-5 h-5" />
                      <span className="text-sm font-medium">{t('requestAccess.roleStudent')}</span>
                    </Button>
                  </div>
                  {role === "student" && (
                    <p className="text-xs text-muted-foreground">
                      {t('requestAccess.studentNote')}
                    </p>
                  )}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="fullName" className="text-sm font-medium">
                    {t('requestAccess.fullName')}
                  </Label>
                  <Input
                    id="fullName"
                    type="text"
                    placeholder={t('placeholder.fullName')}
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    required
                    minLength={3}
                    className="bg-muted/50 border-0"
                    data-testid="input-full-name"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="email" className="text-sm font-medium">
                    {t('requestAccess.email')}
                  </Label>
                  <Input
                    id="email"
                    type="email"
                    placeholder={role === "clinician" ? t('placeholder.emailClinician') : t('placeholder.emailStudent')}
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    className="bg-muted/50 border-0"
                    data-testid="input-email"
                  />
                </div>
                {role === "clinician" && (
                  <div className="space-y-2">
                    <Label
                      htmlFor="practitionerId"
                      className="text-sm font-medium"
                    >
                      {t('requestAccess.practitionerId')}
                    </Label>
                    <Input
                      id="practitionerId"
                      type="text"
                      placeholder={t('placeholder.practitionerId')}
                      value={practitionerId}
                      onChange={(e) => setPractitionerId(e.target.value)}
                      required
                      minLength={3}
                      className="bg-muted/50 border-0"
                      data-testid="input-practitioner-id"
                    />
                  </div>
                )}
                <Button
                  type="submit"
                  className="w-full shadow-lg shadow-primary/25"
                  disabled={isLoading}
                  data-testid="button-submit"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      {t('common.loading')}
                    </>
                  ) : (
                    t('requestAccess.submit')
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
              {t('requestAccess.alreadyHaveAccount')} {t('requestAccess.login')}
            </Button>
          </Link>
        </div>
      </div>
    </div>
  );
}
