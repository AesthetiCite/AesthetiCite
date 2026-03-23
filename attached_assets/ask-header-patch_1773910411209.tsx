/**
 * ASK.TSX HEADER PATCH — Emergency Button + Safety Check Prominence
 * ==================================================================
 *
 * This is a TARGETED PATCH — not a full ask.tsx rewrite.
 * Replace the header nav section in your existing ask.tsx with this block.
 *
 * Find the existing block (around line 2575) that starts with:
 *   <div className="flex items-center gap-2">
 *     {activeSources.length > 0 && (
 *
 * Replace everything inside that outer <div className="flex items-center gap-2">
 * up to (but not including) the closing </header> tag
 * with the JSX below.
 *
 * WHAT CHANGES:
 *   1. Emergency button — red, always visible, links to /emergency
 *   2. Safety Check — promoted from ghost button to outlined button with color
 *   3. "More" dropdown — adds Case Log, Emergency shortcut
 *   4. Mobile sheet — adds Emergency + Case Log
 */

// ── PASTE THIS AS THE HEADER NAV BLOCK ──────────────────────────────────────
// (Replace the <div className="flex items-center gap-2"> ... </div> in the header)

const HeaderNavBlock = `
<div className="flex items-center gap-2">
  {activeSources.length > 0 && (
    <Badge variant="secondary" className="hidden md:flex items-center gap-1.5 text-xs" data-testid="badge-active-sources">
      <BookOpen className="w-3 h-3" />
      {activeSources.length} sources
    </Badge>
  )}

  <Badge variant="secondary" className="hidden md:flex items-center gap-1.5 text-xs">
    <BookOpen className="w-3 h-3" />
    {BRAND.publicationsLabel}
  </Badge>

  {/* ── EVIDENCE ── */}
  <Link href="/ask-oe">
    <Button variant="ghost" size="sm" className="hidden md:flex items-center gap-1.5 text-xs h-8" data-testid="button-ask-oe" title="Structured Evidence View">
      <FileText className="w-3.5 h-3.5" />
      <span>Evidence</span>
    </Button>
  </Link>

  {/* ── SAFETY CHECK — now styled with blue tint ── */}
  <Link href="/safety-check">
    <Button
      variant="outline"
      size="sm"
      className="hidden md:flex items-center gap-1.5 text-xs h-8 border-blue-200 text-blue-700 hover:bg-blue-50 hover:border-blue-400 dark:border-blue-800 dark:text-blue-400"
      data-testid="button-safety-check"
      title="Pre-Procedure Safety Check"
    >
      <ShieldAlert className="w-3.5 h-3.5" />
      <span>Safety Check</span>
    </Button>
  </Link>

  {/* ── EMERGENCY — red, always visible on desktop ── */}
  <Link href="/emergency">
    <Button
      variant="ghost"
      size="sm"
      className="hidden md:flex items-center gap-1.5 text-xs h-8 bg-red-600 hover:bg-red-700 text-white border-0"
      data-testid="button-emergency"
      title="Emergency Complication Protocols"
    >
      <Zap className="w-3.5 h-3.5" />
      <span>Emergency</span>
    </Button>
  </Link>

  <Button
    variant="ghost"
    size="sm"
    className="hidden sm:flex items-center gap-1.5 text-xs h-8"
    onClick={() => setShowClinicalTools(true)}
    data-testid="button-clinical-tools-header"
    title="Clinical Tools"
  >
    <Calculator className="w-3.5 h-3.5" />
    <span>Tools</span>
  </Button>

  {/* ── MOBILE SHEET ── */}
  <Sheet>
    <SheetTrigger asChild>
      <Button variant="ghost" size="icon" className="flex md:hidden h-8 w-8" data-testid="button-mobile-menu">
        <Menu className="w-4 h-4" />
      </Button>
    </SheetTrigger>
    <SheetContent side="right" className="w-72 overflow-y-auto">
      <SheetHeader className="mb-4">
        <SheetTitle className="text-left">Navigation</SheetTitle>
      </SheetHeader>
      <div className="space-y-6 text-sm">

        {/* Emergency — top of mobile nav */}
        <Link href="/emergency" className="flex items-center gap-3 rounded-lg px-3 py-3 bg-red-600 text-white font-bold hover:bg-red-700 transition-colors">
          <Zap className="h-4 w-4" />Emergency Protocols
        </Link>

        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Search</p>
          <div className="space-y-1">
            <Link href="/ask" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><Search className="h-4 w-4" />AesthetiCite Search</Link>
            <Link href="/ask-oe" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><FileText className="h-4 w-4" />Structured Evidence</Link>
            <Link href="/hardest-10" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><BarChart3 className="h-4 w-4" />Challenge Mode</Link>
          </div>
        </div>

        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Safety & Tools</p>
          <div className="space-y-1">
            <Link href="/safety-check" className="flex items-center gap-3 rounded-lg px-3 py-2 bg-blue-50 text-blue-700 font-semibold hover:bg-blue-100 transition-colors rounded-lg">
              <ShieldAlert className="h-4 w-4" />Pre-Procedure Safety
            </Link>
            <Link href="/session-report" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><ClipboardCheck className="h-4 w-4" />Session Safety Report</Link>
            <Link href="/drug-interactions" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><Pill className="h-4 w-4" />Drug Interactions</Link>
            <Link href="/patient-export" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><FileUser className="h-4 w-4" />Patient Export</Link>
            <Link href="/case-log" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><Database className="h-4 w-4" />Case Log</Link>
            <Link href="/visual-counsel" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><Eye className="h-4 w-4" />Visual Counseling</Link>
          </div>
        </div>

        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">My Account</p>
          <div className="space-y-1">
            <Link href="/bookmarks" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><Bookmark className="h-4 w-4" />Saved Answers</Link>
            <Link href="/paper-alerts" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><Bell className="h-4 w-4" />Paper Alerts</Link>
          </div>
        </div>

        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Clinic</p>
          <div className="space-y-1">
            <Link href="/clinic-dashboard" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><LayoutDashboard className="h-4 w-4" />Clinic Dashboard</Link>
            <Link href="/api-keys" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><Key className="h-4 w-4" />API Keys</Link>
          </div>
        </div>
      </div>
    </SheetContent>
  </Sheet>

  {/* ── MORE dropdown (desktop) ── */}
  <DropdownMenu>
    <DropdownMenuTrigger asChild>
      <Button variant="ghost" size="sm" className="hidden md:flex items-center gap-1 text-xs h-8" data-testid="button-more-menu">
        <MoreHorizontal className="w-3.5 h-3.5" />
        <span>More</span>
        <ChevronDown className="w-3 h-3 opacity-50" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" className="w-56">
      <DropdownMenuLabel>Clinical</DropdownMenuLabel>
      <DropdownMenuItem asChild>
        <Link href="/emergency" className="flex items-center gap-2 cursor-pointer text-red-600">
          <Zap className="h-4 w-4" />Emergency Protocols
        </Link>
      </DropdownMenuItem>
      <DropdownMenuItem asChild>
        <Link href="/drug-interactions" className="flex items-center gap-2 cursor-pointer">
          <Pill className="h-4 w-4 text-muted-foreground" />Drug Interaction Checker
        </Link>
      </DropdownMenuItem>
      <DropdownMenuItem asChild>
        <Link href="/session-report" className="flex items-center gap-2 cursor-pointer">
          <ClipboardCheck className="h-4 w-4 text-muted-foreground" />Session Safety Report
        </Link>
      </DropdownMenuItem>
      <DropdownMenuItem asChild>
        <Link href="/patient-export" className="flex items-center gap-2 cursor-pointer">
          <FileUser className="h-4 w-4 text-muted-foreground" />Patient-Readable Export
        </Link>
      </DropdownMenuItem>
      <DropdownMenuItem asChild>
        <Link href="/case-log" className="flex items-center gap-2 cursor-pointer">
          <Database className="h-4 w-4 text-muted-foreground" />Case Log
        </Link>
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuLabel>My Account</DropdownMenuLabel>
      <DropdownMenuItem asChild>
        <Link href="/bookmarks" className="flex items-center gap-2 cursor-pointer">
          <Bookmark className="h-4 w-4 text-muted-foreground" />Saved Answers
        </Link>
      </DropdownMenuItem>
      <DropdownMenuItem asChild>
        <Link href="/paper-alerts" className="flex items-center gap-2 cursor-pointer">
          <Bell className="h-4 w-4 text-muted-foreground" />Paper Alerts
        </Link>
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuLabel>Clinic</DropdownMenuLabel>
      <DropdownMenuItem asChild>
        <Link href="/clinic-dashboard" className="flex items-center gap-2 cursor-pointer">
          <LayoutDashboard className="h-4 w-4 text-muted-foreground" />Clinic Dashboard
        </Link>
      </DropdownMenuItem>
      <DropdownMenuItem asChild>
        <Link href="/api-keys" className="flex items-center gap-2 cursor-pointer">
          <Key className="h-4 w-4 text-muted-foreground" />API Keys
        </Link>
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>

  <UsageIndicator />
  <ThemeToggle />
  <LanguageSelector />

  {/* User dropdown stays as-is */}
</div>
`;

// ALSO: Add this import at the top of ask.tsx (add to existing import line):
// import { Database } from "lucide-react";   ← add Database to the lucide imports
// import { Zap } from "lucide-react";        ← Zap is already imported

export {};  // This file is for documentation — paste the JSX directly into ask.tsx
