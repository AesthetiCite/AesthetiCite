import { useState } from "react";
import { useLocation, Link } from "wouter";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Loader2, FileText, Sparkles, Shield } from "lucide-react";
import { login, setToken, getMe } from "@/lib/auth";
import { useToast } from "@/hooks/use-toast";
import { ThemeToggle } from "@/components/theme-toggle";
import { LanguageSelector } from "@/components/language-selector";
import { useLocale } from "@/hooks/use-locale";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [, setLocation] = useLocation();
  const { toast } = useToast();
  const { t } = useLocale();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setIsLoading(true);

    try {
      const token = await login(email, password);
      setToken(token);
      await getMe(token);
      setLocation("/");
    } catch (err) {
      toast({
        variant: "destructive",
        title: t('login.failed'),
        description: err instanceof Error ? err.message : t('login.invalidCredentials'),
      });
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-muted/30 flex">
      <div className="absolute top-4 right-4 flex items-center gap-2 z-10">
        <LanguageSelector />
        <ThemeToggle />
      </div>
      
      <div className="hidden lg:flex lg:w-1/2 bg-gradient-to-br from-primary/5 via-primary/10 to-primary/5 items-center justify-center p-12 relative overflow-hidden">
        <div className="ambient-glow w-64 h-64 bg-primary/20 top-20 -left-10 absolute" />
        <div className="ambient-glow w-48 h-48 bg-accent/15 bottom-20 right-10 absolute" style={{ animationDelay: '2s' }} />
        <div className="max-w-md relative">
          <div className="flex flex-col items-center mb-8">
            <img 
              src="/aestheticite-logo.png" 
              alt="AesthetiCite" 
              className="w-36 h-36 object-contain drop-shadow-lg"
              data-testid="img-login-logo"
            />
          </div>
          
          <h2 className="text-3xl font-bold tracking-tight mb-4">
            {t('landing.headline')}
          </h2>
          <p className="text-muted-foreground text-lg mb-8 leading-relaxed">
            {t('landing.subheadline')}
          </p>
          
          <div className="space-y-4">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0">
                <FileText className="w-5 h-5 text-primary" />
              </div>
              <div>
                <h3 className="font-semibold">{t('landing.verifiedSources')}</h3>
                <p className="text-sm text-muted-foreground">{t('landing.verifiedSourcesDesc')}</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0">
                <Sparkles className="w-5 h-5 text-primary" />
              </div>
              <div>
                <h3 className="font-semibold">{t('landing.aiPoweredSearch')}</h3>
                <p className="text-sm text-muted-foreground">{t('landing.aiPoweredSearchDesc')}</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0">
                <Shield className="w-5 h-5 text-primary" />
              </div>
              <div>
                <h3 className="font-semibold">{t('landing.evidenceFirst')}</h3>
                <p className="text-sm text-muted-foreground">{t('landing.evidenceFirstDesc')}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div className="lg:hidden flex flex-col items-center mb-8">
            <img 
              src="/aestheticite-logo.png" 
              alt="AesthetiCite" 
              className="w-32 h-32 object-contain mb-2"
              data-testid="img-login-logo-mobile"
            />
          </div>

          <div className="text-center mb-6 hidden lg:block">
            <h1 className="text-2xl font-bold tracking-tight" data-testid="text-card-title">{t('login.title')}</h1>
            <p className="text-muted-foreground text-sm mt-1">{t('login.subtitle')}</p>
          </div>

          <button
            type="button"
            data-testid="button-demo-login"
            onClick={() => { setEmail("demo@aestheticite.com"); setPassword("Demo2026!"); }}
            className="w-full mb-3 flex items-center justify-between gap-3 rounded-xl border border-primary/25 bg-primary/5 hover:bg-primary/10 px-4 py-3 transition-colors group"
          >
            <div className="text-left">
              <p className="text-xs font-bold text-primary">Try the demo</p>
              <p className="text-[11px] text-muted-foreground font-mono">demo@aestheticite.com</p>
            </div>
            <span className="text-[11px] font-semibold text-primary/70 group-hover:text-primary transition-colors">
              Fill credentials →
            </span>
          </button>

          <Card className="border-0 shadow-xl bg-card/80 backdrop-blur">
            <CardContent className="p-6">
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="email" className="text-sm font-medium">{t('login.email')}</Label>
                  <Input
                    id="email"
                    type="email"
                    placeholder={t('placeholder.emailLogin')}
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    className="bg-muted/50 border-0"
                    data-testid="input-email"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="password" className="text-sm font-medium">{t('login.password')}</Label>
                  <Input
                    id="password"
                    type="password"
                    placeholder={t('placeholder.password')}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    className="bg-muted/50 border-0"
                    data-testid="input-password"
                  />
                </div>
                <Button 
                  type="submit" 
                  className="w-full shadow-lg shadow-primary/25" 
                  disabled={isLoading} 
                  data-testid="button-login"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      {t('common.loading')}
                    </>
                  ) : (
                    t('login.submit')
                  )}
                </Button>
              </form>
            </CardContent>
          </Card>

          <div className="text-center mt-6">
            <Link href="/request-access">
              <Button variant="ghost" size="sm" data-testid="link-request-access">
                {t('login.noAccount')} {t('login.requestAccess')}
              </Button>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
