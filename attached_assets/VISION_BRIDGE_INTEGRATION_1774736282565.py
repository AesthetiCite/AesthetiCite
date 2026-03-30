"""
Integration patch for app/api/visual_counseling.py
====================================================
Find the section in your /visual/analyse endpoint (or the streaming analyse handler)
where GPT-4o returns its analysis text. Add the 5 lines marked with # ← ADD.

This is a minimal, non-destructive change — it only appends a new key to the
existing response dict / SSE stream. Nothing else changes.

───────────────────────────────────────────────────────────────────────────
PATCH 1: Import at the top of visual_counseling.py
───────────────────────────────────────────────────────────────────────────
"""

# At the top of app/api/visual_counseling.py, add:
from app.engine.vision_protocol_bridge import (    # ← ADD
    detect_protocols_from_vision_text,             # ← ADD
    build_protocol_alert_sse,                      # ← ADD
)                                                  # ← ADD


# ───────────────────────────────────────────────────────────────────────────
# PATCH 2a: Non-streaming /visual/analyse endpoint
# Find the return statement that builds the JSON response, e.g.:
#
#   return {
#       "analysis": analysis_text,
#       "findings": ...,
#       ...
#   }
#
# Replace with:
# ───────────────────────────────────────────────────────────────────────────

# BEFORE (example — match your actual variable names):
# return {
#     "analysis": analysis_text,
#     "findings": findings,
# }

# AFTER:
triggered_protocols = detect_protocols_from_vision_text(  # ← ADD
    analysis_text, query=user_question                     # ← ADD (use your actual var names)
)                                                          # ← ADD

# return {
#     "analysis": analysis_text,
#     "findings": findings,
#     "triggered_protocols": triggered_protocols,          # ← ADD
# }


# ───────────────────────────────────────────────────────────────────────────
# PATCH 2b: Streaming analyse endpoint (SSE)
# After the LLM/GPT-4o stream is exhausted and you have the full analysis_text:
# ───────────────────────────────────────────────────────────────────────────

# AFTER your existing stream-complete / done event:

async def _example_stream_patch(analysis_text: str, user_question: str):
    """
    Illustrative — replace variable names with your actual ones.
    Add this block immediately after the LLM streaming loop ends,
    before you close the SSE generator.
    """
    import json

    # ... existing streaming code above ...

    # ── Vision Protocol Bridge ───────────────────────────────────────────
    triggered = detect_protocols_from_vision_text(     # ← ADD
        analysis_text, query=user_question             # ← ADD
    )                                                  # ← ADD
    if triggered:                                      # ← ADD
        alert = build_protocol_alert_sse(triggered)    # ← ADD
        yield f"data: {json.dumps(alert)}\n\n"         # ← ADD
    # ── End Vision Protocol Bridge ───────────────────────────────────────


# ───────────────────────────────────────────────────────────────────────────
# PATCH 3: Frontend SSE handler (TypeScript / React)
# In the file that processes SSE events from /api/ask/visual/stream,
# add a case for "protocol_alert":
# ───────────────────────────────────────────────────────────────────────────

FRONTEND_SSE_PATCH = """
// In your SSE parsing switch/if block, add:

case "protocol_alert":
  setTriggeredProtocols(data.triggered_protocols ?? []);
  break;

// And in your component state:
const [triggeredProtocols, setTriggeredProtocols] = useState<TriggeredProtocol[]>([]);

// And in your JSX, after the analysis text block:
<ProtocolAlert protocols={triggeredProtocols} />
"""

# ───────────────────────────────────────────────────────────────────────────
# File placement
# ───────────────────────────────────────────────────────────────────────────

FILE_PLACEMENT = """
New files to add to the repo:

  app/engine/vision_protocol_bridge.py     ← backend bridge (Python)
  client/src/components/vision/ProtocolAlert.tsx  ← frontend alert component

No existing files need to be replaced — only two targeted insertions
into visual_counseling.py (import + 3-5 lines in the analyse handler).
"""
