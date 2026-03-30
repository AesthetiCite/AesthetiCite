/**
 * AESTHETICITE UX FIXES
 * =====================
 * File: client/src/pages/ask.tsx — header and navigation section
 *
 * CHANGES:
 * 1. Logo becomes a Link back to /ask (home)
 * 2. Language selector added to desktop header (always visible)
 * 3. Emergency promoted to primary header — red, always visible
 * 4. Vision renamed and linked correctly to /vision-analysis
 * 5. Challenge demoted to More dropdown (not daily use)
 * 6. Header layout: Emergency | Safety | Vision | Tools | Language | More ▾
 *
 * Apply by replacing the <header> block in ask.tsx
 * Search for: <header className="border-b glass-panel sticky top-0 z-50 flex-shrink-0">
 * Replace the entire header with the block below.
 */

// ─── PASTE THIS ENTIRE BLOCK to replace the existing <header> ──────────────

/*
<header className="border-b glass-panel sticky top-0 z-50 flex-shrink-0">
  <div className="px-4 sm:px-6 py-3 flex items-center justify-between gap-4">

    {/* LEFT: sidebar toggle + logo (logo is now a link back to /ask) */}
    <div className="flex items-center gap-3">
      {!sidebarOpen && (
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setSidebarOpen(true)}
          data-testid="button-open-sidebar"
        >
          <PanelLeft className="w-4 h-4" />
        </Button>
      )}
      {/* FIX 1: Logo is now a Link back to /ask */}
      <Link href="/ask">
        <div className="hidden sm:flex items-center gap-2.5 cursor-pointer hover:opacity-80 transition-opacity">
          <img
            src="/aestheticite-logo.png"
            alt="AesthetiCite"
            className="w-8 h-8 object-contain rounded-lg"
            data-testid="img-header-logo"
          />
          <span className="text-lg font-semibold tracking-tight">{BRAND.name}</span>
        </div>
      </Link>
    </div>

    {/* RIGHT: primary nav */}
    <div className="flex items-center gap-1.5">

      {/* FIX 3: Emergency — always visible, red accent */}
      <Link href="/emergency">
        <Button
          variant="ghost"
          size="sm"
          className="hidden md:flex items-center gap-1.5 text-xs h-8 text-red-600 hover:text-red-700 hover:bg-red-50 font-semibold"
          data-testid="button-emergency"
          title="Emergency protocols — vascular occlusion, anaphylaxis"
        >
          <Zap className="w-3.5 h-3.5" />
          <span>Emergency</span>
        </Button>
      </Link>

      {/* Safety check */}
      <Link href="/safety-check">
        <Button
          variant="ghost"
          size="sm"
          className="hidden md:flex items-center gap-1.5 text-xs h-8"
          data-testid="button-safety-check"
          title="Pre-Procedure Safety Check"
        >
          <ShieldAlert className="w-3.5 h-3.5" />
          <span>Safety</span>
        </Button>
      </Link>

      {/* FIX 4: Vision — correctly labelled and linked to /vision-analysis */}
      <Link href="/vision-analysis">
        <Button
          variant="ghost"
          size="sm"
          className="hidden md:flex items-center gap-1.5 text-xs h-8"
          data-testid="button-vision-analysis"
          title="Complication Vision Engine"
        >
          <Eye className="w-3.5 h-3.5" />
          <span>Vision</span>
        </Button>
      </Link>

      {/* Tools */}
      <Button
        variant="ghost"
        size="sm"
        className="hidden md:flex items-center gap-1.5 text-xs h-8"
        onClick={() => setShowClinicalTools(true)}
        data-testid="button-clinical-tools-header"
        title="Clinical Tools"
      >
        <Calculator className="w-3.5 h-3.5" />
        <span>Tools</span>
      </Button>

      {/* FIX 2: Language selector — always visible on desktop */}
      <div className="hidden md:flex">
        <LanguageSelector />
      </div>

      {/* More dropdown — secondary features */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className="hidden md:flex items-center gap-1 text-xs h-8"
            data-testid="button-more-dropdown"
          >
            <MoreHorizontal className="w-4 h-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-52">
          <DropdownMenuLabel className="text-xs text-muted-foreground">Evidence</DropdownMenuLabel>
          <DropdownMenuItem asChild>
            <Link href="/ask-oe" className="flex items-center gap-2 cursor-pointer">
              <FileText className="w-3.5 h-3.5" />
              Structured Evidence
            </Link>
          </DropdownMenuItem>
          {/* FIX 5: Challenge moved here — not daily use */}
          <DropdownMenuItem asChild>
            <Link href="/hardest-10" className="flex items-center gap-2 cursor-pointer">
              <BarChart3 className="w-3.5 h-3.5" />
              Challenge Mode
            </Link>
          </DropdownMenuItem>

          <DropdownMenuSeparator />
          <DropdownMenuLabel className="text-xs text-muted-foreground">Clinic</DropdownMenuLabel>
          <DropdownMenuItem asChild>
            <Link href="/drug-interactions" className="flex items-center gap-2 cursor-pointer">
              <Pill className="w-3.5 h-3.5" />
              Drug Interactions
            </Link>
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            <Link href="/session-report" className="flex items-center gap-2 cursor-pointer">
              <ClipboardCheck className="w-3.5 h-3.5" />
              Session Report
            </Link>
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            <Link href="/patient-export" className="flex items-center gap-2 cursor-pointer">
              <FileUser className="w-3.5 h-3.5" />
              Patient Export
            </Link>
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            <Link href="/bookmarks" className="flex items-center gap-2 cursor-pointer">
              <Bookmark className="w-3.5 h-3.5" />
              Saved Answers
            </Link>
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            <Link href="/case-log" className="flex items-center gap-2 cursor-pointer">
              <ClipboardCheck className="w-3.5 h-3.5" />
              Case Log
            </Link>
          </DropdownMenuItem>

          <DropdownMenuSeparator />
          <DropdownMenuLabel className="text-xs text-muted-foreground">Account</DropdownMenuLabel>
          <DropdownMenuItem asChild>
            <Link href="/clinic-dashboard" className="flex items-center gap-2 cursor-pointer">
              <LayoutDashboard className="w-3.5 h-3.5" />
              Clinic Dashboard
            </Link>
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            <Link href="/paper-alerts" className="flex items-center gap-2 cursor-pointer">
              <Bell className="w-3.5 h-3.5" />
              Paper Alerts
            </Link>
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            <Link href="/api-keys" className="flex items-center gap-2 cursor-pointer">
              <Key className="w-3.5 h-3.5" />
              API Keys
            </Link>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Mobile sheet — full nav */}
      <Sheet>
        <SheetTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="flex md:hidden h-8 w-8"
            data-testid="button-mobile-menu"
          >
            <Menu className="w-4 h-4" />
          </Button>
        </SheetTrigger>
        <SheetContent side="right" className="w-72 overflow-y-auto">
          <SheetHeader className="mb-4">
            <SheetTitle className="text-left">Navigation</SheetTitle>
          </SheetHeader>
          <div className="space-y-5 text-sm">

            {/* Language selector at TOP of mobile sheet — FIX 2 */}
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Language</p>
              <LanguageSelector />
            </div>

            {/* Emergency — prominent */}
            <div>
              <Link href="/emergency" className="flex items-center gap-3 rounded-lg px-3 py-2.5 bg-red-50 text-red-700 font-semibold hover:bg-red-100 transition-colors">
                <Zap className="h-4 w-4" /> Emergency
              </Link>
            </div>

            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Clinical</p>
              <div className="space-y-1">
                <Link href="/ask" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><Search className="h-4 w-4" />Search</Link>
                <Link href="/safety-check" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><ShieldAlert className="h-4 w-4" />Safety Check</Link>
                <Link href="/vision-analysis" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><Eye className="h-4 w-4" />Vision Analysis</Link>
                <Link href="/drug-interactions" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><Pill className="h-4 w-4" />Drug Interactions</Link>
              </div>
            </div>

            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Session</p>
              <div className="space-y-1">
                <Link href="/session-report" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><ClipboardCheck className="h-4 w-4" />Session Report</Link>
                <Link href="/patient-export" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><FileUser className="h-4 w-4" />Patient Export</Link>
                <Link href="/bookmarks" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><Bookmark className="h-4 w-4" />Saved Answers</Link>
                <Link href="/case-log" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><ClipboardCheck className="h-4 w-4" />Case Log</Link>
              </div>
            </div>

            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">My Account</p>
              <div className="space-y-1">
                <Link href="/clinic-dashboard" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><LayoutDashboard className="h-4 w-4" />Clinic Dashboard</Link>
                <Link href="/api-keys" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><Key className="h-4 w-4" />API Keys</Link>
              </div>
            </div>

          </div>
        </SheetContent>
      </Sheet>

    </div>
  </div>
</header>
*/

// ─── ROUTING FIX ────────────────────────────────────────────────────────────
/**
 * File: server/routes.ts or App.tsx — wherever the post-login redirect is set
 *
 * FIX: Login should route directly to /ask, not /home or /start
 *
 * Find the post-login redirect (usually in login.tsx or auth handler):
 *
 * BEFORE:
 *   setLocation("/home");
 *   // or
 *   setLocation("/start");
 *   // or
 *   router.push("/");
 *
 * AFTER:
 *   setLocation("/ask");
 *
 * Also update App.tsx default route:
 *
 * BEFORE:
 *   <Route path="/">{() => <ProtectedRoute component={HomePage} />}</Route>
 *
 * AFTER:
 *   <Route path="/">{() => <Redirect to="/ask" />}</Route>
 */

// ─── SIDEBAR FIX ────────────────────────────────────────────────────────────
/**
 * In the sidebar (left panel of ask.tsx), add a Home/Tools link at the top
 * below the New Search button, so clinicians can access the tools hub:
 *
 * Find the sidebar <div className="p-3 space-y-2"> block and add:
 *
 * <Link href="/home">
 *   <Button className="w-full justify-start gap-2" variant="ghost">
 *     <LayoutDashboard className="w-4 h-4" />
 *     All Tools
 *   </Button>
 * </Link>
 *
 * This gives a clear path from /ask back to the tools hub.
 */

export {};
