/**
 * AesthetiCite — ask.tsx Complete Patch
 * client/src/ask-patch-final.tsx
 *
 * Six independent str_replace operations on ask.tsx.
 * Each block shows the EXACT text to find (unique in the file)
 * and the exact text to replace it with.
 *
 * Apply with your editor's find-and-replace, or use the
 * shell commands at the bottom of this file.
 */


// ─────────────────────────────────────────────────────────────────────────────
// PATCH 1 — Add two imports
// Find the existing import that ends the imports block (last import line).
// Add these two lines after it.
//
// FIND (last import line in ask.tsx — exact):
// ─────────────────────────────────────────────────────────────────────────────

const PATCH_1_FIND = `import { isAuthenticated } from "@/lib/auth";`;

const PATCH_1_REPLACE = `import { isAuthenticated } from "@/lib/auth";
import { SidebarSafetyNav } from "@/components/sidebar-safety-nav";
import { ProtocolCard, type ProtocolCardData } from "@/components/protocol-card";`;


// ─────────────────────────────────────────────────────────────────────────────
// PATCH 2 — Extend ChatMessage interface
// ─────────────────────────────────────────────────────────────────────────────

const PATCH_2_FIND = `  isRefusal?: boolean;
  refusalReason?: string;
  refusalCode?: string;
}`;

const PATCH_2_REPLACE = `  isRefusal?: boolean;
  refusalReason?: string;
  refusalCode?: string;
  protocolCard?: ProtocolCardData | null;
}`;


// ─────────────────────────────────────────────────────────────────────────────
// PATCH 3A — Add protocol_card case to askQuestionStream (standard mode)
// ─────────────────────────────────────────────────────────────────────────────

const PATCH_3A_FIND = `            case "refusal":
              callbacks.onError(data.reason);
              break;
          }`;

const PATCH_3A_REPLACE = `            case "refusal":
              callbacks.onError(data.reason);
              break;
            case "protocol_card":
              callbacks.onProtocolCard?.(data as ProtocolCardData);
              break;
          }`;


// ─────────────────────────────────────────────────────────────────────────────
// PATCH 3B — Add protocol_card case to askQuestionStreamV2 (enhanced mode)
// ─────────────────────────────────────────────────────────────────────────────

const PATCH_3B_FIND = `              case "error":
                callbacks.onError(data.message || data.data || "Error");
                break;
            }`;

const PATCH_3B_REPLACE = `              case "error":
                callbacks.onError(data.message || data.data || "Error");
                break;
              case "protocol_card":
                callbacks.onProtocolCard?.(data as ProtocolCardData);
                break;
            }`;


// ─────────────────────────────────────────────────────────────────────────────
// PATCH 4 — Add onProtocolCard to StreamCallbacks interface
// ─────────────────────────────────────────────────────────────────────────────

const PATCH_4_FIND = `export interface StreamCallbacks {
  onToken: (token: string) => void;
  onMeta: (citations: Citation[], requestId: string, extra?: StreamMetaData) => void;
  onRelated: (questions: string[]) => void;
  onDone: (fullAnswer: string) => void;
  onError: (error: string) => void;
}`;

const PATCH_4_REPLACE = `export interface StreamCallbacks {
  onToken: (token: string) => void;
  onMeta: (citations: Citation[], requestId: string, extra?: StreamMetaData) => void;
  onRelated: (questions: string[]) => void;
  onDone: (fullAnswer: string) => void;
  onError: (error: string) => void;
  onProtocolCard?: (card: ProtocolCardData) => void;
}`;


// ─────────────────────────────────────────────────────────────────────────────
// PATCH 5A — Wire onProtocolCard in handleAsk enhanced mode (askQuestionStreamV2)
// ─────────────────────────────────────────────────────────────────────────────

const PATCH_5A_FIND = `          onError: (error) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId ? { ...m, content: \`Error: \${error}\`, isStreaming: false } : m
              )
            );
            toast({ variant: "destructive", title: "Query failed", description: error });
            setIsLoading(false);
          },
        }, convId, controller.signal);`;

const PATCH_5A_REPLACE = `          onProtocolCard: (card) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId ? { ...m, protocolCard: card } : m
              )
            );
          },
          onError: (error) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId ? { ...m, content: \`Error: \${error}\`, isStreaming: false } : m
              )
            );
            toast({ variant: "destructive", title: "Query failed", description: error });
            setIsLoading(false);
          },
        }, convId, controller.signal);`;


// ─────────────────────────────────────────────────────────────────────────────
// PATCH 5B — Wire onProtocolCard in handleAsk standard mode (askQuestionStream)
// ─────────────────────────────────────────────────────────────────────────────

const PATCH_5B_FIND = `          onError: (error) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId ? { ...m, content: \`Error: \${error}\`, isStreaming: false } : m
              )
            );
            toast({ variant: "destructive", title: "Query failed", description: error });
            setIsLoading(false);
          },
        }, convId);`;

const PATCH_5B_REPLACE = `          onProtocolCard: (card) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId ? { ...m, protocolCard: card } : m
              )
            );
          },
          onError: (error) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId ? { ...m, content: \`Error: \${error}\`, isStreaming: false } : m
              )
            );
            toast({ variant: "destructive", title: "Query failed", description: error });
            setIsLoading(false);
          },
        }, convId);`;


// ─────────────────────────────────────────────────────────────────────────────
// PATCH 6 — Insert <SidebarSafetyNav /> above <ScrollArea>
// ─────────────────────────────────────────────────────────────────────────────

const PATCH_6_FIND = `          <ScrollArea className="flex-1 px-3">`;

const PATCH_6_REPLACE = `          <SidebarSafetyNav />
          <ScrollArea className="flex-1 px-3">`;


// ─────────────────────────────────────────────────────────────────────────────
// PATCH 7 — Render <ProtocolCard /> below <StructuredAnswer />
// ─────────────────────────────────────────────────────────────────────────────

const PATCH_7_FIND = `                        <StructuredAnswer
                          msg={msg}
                          lastQuestion={lastQuestion}
                          onRelatedQuestion={handleRelatedQuestion}
                          onCopyNote={copyNote}
                          copiedNote={copiedNote}
                        />`;

const PATCH_7_REPLACE = `                        <StructuredAnswer
                          msg={msg}
                          lastQuestion={lastQuestion}
                          onRelatedQuestion={handleRelatedQuestion}
                          onCopyNote={copyNote}
                          copiedNote={copiedNote}
                        />
                        {msg.protocolCard && !msg.isStreaming && (
                          <ProtocolCard data={msg.protocolCard} />
                        )}`;


// ─────────────────────────────────────────────────────────────────────────────
// PATCH 8 — Add Complication Protocols to More dropdown
// ─────────────────────────────────────────────────────────────────────────────

const PATCH_8_FIND = `                  <DropdownMenuLabel>Clinical</DropdownMenuLabel>
                  <DropdownMenuItem asChild>
                    <Link href="/drug-interactions" className="flex items-center gap-2 cursor-pointer">
                      <Pill className="h-4 w-4 text-muted-foreground" />Drug Interaction Checker
                    </Link>
                  </DropdownMenuItem>`;

const PATCH_8_REPLACE = `                  <DropdownMenuLabel>Clinical</DropdownMenuLabel>
                  <DropdownMenuItem asChild>
                    <Link href="/complications" className="flex items-center gap-2 cursor-pointer">
                      <AlertTriangle className="h-4 w-4 text-muted-foreground" />Complication Protocols
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <Link href="/drug-interactions" className="flex items-center gap-2 cursor-pointer">
                      <Pill className="h-4 w-4 text-muted-foreground" />Drug Interaction Checker
                    </Link>
                  </DropdownMenuItem>`;


// ─────────────────────────────────────────────────────────────────────────────
// PATCH 9 — Add Complication Protocols to mobile Sheet nav
// ─────────────────────────────────────────────────────────────────────────────

const PATCH_9_FIND = `                        <Link href="/safety-check" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><ShieldAlert className="h-4 w-4" />Pre-Procedure Safety</Link>
                        <Link href="/session-report" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><ClipboardCheck className="h-4 w-4" />Session Safety Report</Link>`;

const PATCH_9_REPLACE = `                        <Link href="/safety-check" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><ShieldAlert className="h-4 w-4" />Pre-Procedure Safety</Link>
                        <Link href="/complications" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><AlertTriangle className="h-4 w-4" />Complication Protocols</Link>
                        <Link href="/session-report" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><ClipboardCheck className="h-4 w-4" />Session Safety Report</Link>`;


// ─────────────────────────────────────────────────────────────────────────────
// Shell script — apply all patches automatically
// Save this section as apply-patches.sh and run: bash apply-patches.sh
// ─────────────────────────────────────────────────────────────────────────────

/*
#!/bin/bash
# apply-patches.sh
# Run from the project root. Requires Node.js.

node - <<'EOF'
const fs = require('fs');
const path = require('path');

const ASK_PATH = path.join('client', 'src', 'pages', 'ask.tsx');

// Read current file — also handles ask.tsx if the page is in /pages/
let file = '';
const candidates = [
  path.join('client', 'src', 'pages', 'ask.tsx'),
  path.join('client', 'src', 'App.tsx'),  // not this one
];
for (const c of candidates) {
  if (fs.existsSync(c)) { file = fs.readFileSync(c, 'utf8'); break; }
}
if (!file) { console.error('ask.tsx not found'); process.exit(1); }

const patches = [
  // PATCH 1 — imports
  [
    'import { isAuthenticated } from "@/lib/auth";',
    'import { isAuthenticated } from "@/lib/auth";\nimport { SidebarSafetyNav } from "@/components/sidebar-safety-nav";\nimport { ProtocolCard, type ProtocolCardData } from "@/components/protocol-card";'
  ],
  // PATCH 2 — ChatMessage interface
  [
    '  isRefusal?: boolean;\n  refusalReason?: string;\n  refusalCode?: string;\n}',
    '  isRefusal?: boolean;\n  refusalReason?: string;\n  refusalCode?: string;\n  protocolCard?: ProtocolCardData | null;\n}'
  ],
  // PATCH 3A — protocol_card case in askQuestionStream
  [
    '            case "refusal":\n              callbacks.onError(data.reason);\n              break;\n          }',
    '            case "refusal":\n              callbacks.onError(data.reason);\n              break;\n            case "protocol_card":\n              callbacks.onProtocolCard?.(data);\n              break;\n          }'
  ],
  // PATCH 3B — protocol_card case in askQuestionStreamV2
  [
    '              case "error":\n                callbacks.onError(data.message || data.data || "Error");\n                break;\n            }',
    '              case "error":\n                callbacks.onError(data.message || data.data || "Error");\n                break;\n              case "protocol_card":\n                callbacks.onProtocolCard?.(data);\n                break;\n            }'
  ],
  // PATCH 4 — StreamCallbacks interface
  [
    '  onError: (error: string) => void;\n}',
    '  onError: (error: string) => void;\n  onProtocolCard?: (card: any) => void;\n}'
  ],
  // PATCH 6 — SidebarSafetyNav
  [
    '          <ScrollArea className="flex-1 px-3">',
    '          <SidebarSafetyNav />\n          <ScrollArea className="flex-1 px-3">'
  ],
  // PATCH 7 — ProtocolCard render
  [
    '                        <StructuredAnswer\n                          msg={msg}\n                          lastQuestion={lastQuestion}\n                          onRelatedQuestion={handleRelatedQuestion}\n                          onCopyNote={copyNote}\n                          copiedNote={copiedNote}\n                        />',
    '                        <StructuredAnswer\n                          msg={msg}\n                          lastQuestion={lastQuestion}\n                          onRelatedQuestion={handleRelatedQuestion}\n                          onCopyNote={copyNote}\n                          copiedNote={copiedNote}\n                        />\n                        {msg.protocolCard && !msg.isStreaming && (\n                          <ProtocolCard data={msg.protocolCard} />\n                        )}'
  ],
  // PATCH 8 — More dropdown
  [
    '                  <DropdownMenuLabel>Clinical</DropdownMenuLabel>\n                  <DropdownMenuItem asChild>\n                    <Link href="/drug-interactions"',
    '                  <DropdownMenuLabel>Clinical</DropdownMenuLabel>\n                  <DropdownMenuItem asChild>\n                    <Link href="/complications" className="flex items-center gap-2 cursor-pointer">\n                      <AlertTriangle className="h-4 w-4 text-muted-foreground" />Complication Protocols\n                    </Link>\n                  </DropdownMenuItem>\n                  <DropdownMenuItem asChild>\n                    <Link href="/drug-interactions"'
  ],
  // PATCH 9 — Mobile sheet
  [
    '<Link href="/safety-check" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><ShieldAlert className="h-4 w-4" />Pre-Procedure Safety</Link>\n                        <Link href="/session-report"',
    '<Link href="/safety-check" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><ShieldAlert className="h-4 w-4" />Pre-Procedure Safety</Link>\n                        <Link href="/complications" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors"><AlertTriangle className="h-4 w-4" />Complication Protocols</Link>\n                        <Link href="/session-report"'
  ],
];

let patched = file;
let count = 0;
for (const [find, replace] of patches) {
  if (patched.includes(find)) {
    patched = patched.replace(find, replace);
    count++;
    console.log(`✓ Patch ${count} applied`);
  } else {
    console.warn(`⚠ Patch not found (may already be applied): ${find.slice(0, 60)}...`);
  }
}

fs.writeFileSync(ASK_PATH, patched);
console.log(`\nDone — ${count} patches applied to ${ASK_PATH}`);
EOF
*/


// ─────────────────────────────────────────────────────────────────────────────
// Summary of all changes when applied:
//
//  ask.tsx:
//    PATCH 1  — imports SidebarSafetyNav + ProtocolCard
//    PATCH 2  — adds protocolCard field to ChatMessage
//    PATCH 3A — protocol_card SSE case in askQuestionStream
//    PATCH 3B — protocol_card SSE case in askQuestionStreamV2
//    PATCH 4  — onProtocolCard callback in StreamCallbacks
//    PATCH 5A — onProtocolCard wired in handleAsk enhanced mode
//    PATCH 5B — onProtocolCard wired in handleAsk standard mode
//    PATCH 6  — <SidebarSafetyNav /> above <ScrollArea>
//    PATCH 7  — <ProtocolCard /> below <StructuredAnswer />
//    PATCH 8  — Complication Protocols in More dropdown
//    PATCH 9  — Complication Protocols in mobile Sheet nav
//
//  App.tsx:        already delivered (adds /complications route)
//  routes.ts:      see routes-patch-final.ts (sanitizer + stream routes)
//  hnsw_migration.py: run once against live DB
// ─────────────────────────────────────────────────────────────────────────────

export {};
