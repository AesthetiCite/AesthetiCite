import { Globe, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useLocale } from '@/hooks/use-locale';
import { locales, localeNames, type Locale } from '@/lib/i18n';

const LANG_GROUPS = [
  { label: "European", langs: ["en", "fr", "de", "es", "pt", "it", "nl", "pl", "ro", "sv", "da"] },
  { label: "Middle East & Asia", langs: ["ar", "tr", "ru", "fa"] },
  { label: "South & East Asia", langs: ["zh", "ja", "ko", "hi", "bn", "ta", "ur", "mr", "gu", "th", "id", "vi"] },
  { label: "Other", langs: ["sw", "ha", "pa", "te"] },
];

export function LanguageSelector() {
  const { locale, setLocale } = useLocale();
  const currentName = localeNames[locale] ?? locale.toUpperCase();
  const shortCode = locale.toUpperCase();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="flex items-center gap-1.5 h-8 px-2.5 text-xs font-medium"
          data-testid="button-language-selector"
        >
          <Globe className="h-3.5 w-3.5 flex-shrink-0" />
          <span>{shortCode}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-h-96 overflow-y-auto w-52">
        <DropdownMenuLabel className="text-xs text-muted-foreground font-normal pb-1">
          Select language — 25 available
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {LANG_GROUPS.map((group) => {
          const groupLangs = group.langs.filter((l) => locales.includes(l as Locale));
          if (groupLangs.length === 0) return null;
          return (
            <div key={group.label}>
              <DropdownMenuLabel className="text-[10px] text-muted-foreground/60 uppercase tracking-wider px-2 py-1">
                {group.label}
              </DropdownMenuLabel>
              {groupLangs.map((loc) => (
                <DropdownMenuItem
                  key={loc}
                  onClick={() => setLocale(loc as Locale)}
                  className="flex items-center justify-between cursor-pointer"
                  data-testid={`menu-item-lang-${loc}`}
                >
                  <span className={locale === loc ? "font-medium" : ""}>{localeNames[loc as Locale]}</span>
                  {locale === loc && <Check className="h-3.5 w-3.5 text-primary flex-shrink-0" />}
                </DropdownMenuItem>
              ))}
            </div>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

interface LanguageSelectorFullProps {
  className?: string;
}

export function LanguageSelectorFull({ className }: LanguageSelectorFullProps) {
  const { locale, setLocale } = useLocale();

  return (
    <div className={className}>
      <label className="block text-sm font-medium mb-2">Language</label>
      <select
        value={locale}
        onChange={(e) => setLocale(e.target.value as Locale)}
        className="w-full p-2 border rounded-md bg-background"
        data-testid="select-language"
      >
        {locales.map((loc) => (
          <option key={loc} value={loc}>
            {localeNames[loc]}
          </option>
        ))}
      </select>
    </div>
  );
}
