"""
AesthetiCite Vision — 10 Technical Improvements Integration Guide
=================================================================

FILES DELIVERED
───────────────
  vision_engine_v2.py   → app/api/vision_engine_v2.py       (improvements 1,2,3,5,7,8,9,10)
  vision_landmarks.py   → app/api/vision_landmarks.py        (improvement 4)
  vision-sw.js          → public/vision-sw.js                 (improvement 6)
  [inside vision-sw.js] → VisionStreamingAnalysis.tsx         (improvement 2 frontend)

IMPROVEMENT MAP
───────────────
  1  Model router (Claude 3.7 / GPT-4.5)       vision_engine_v2.py  _get_vision_model()
  2  Real-time streaming output                 vision_engine_v2.py  POST /visual/v2/stream
  3  Multi-image single API call                vision_engine_v2.py  POST /visual/v2/multi-analyse
  4  Anatomical landmark detection              vision_landmarks.py  POST /visual/landmark-analyse
  5  Auto image preprocessing                  vision_engine_v2.py  preprocess_image()
  6  Offline PWA Vision mode                   vision-sw.js         service worker + IndexedDB
  7  Video clip analysis                        vision_engine_v2.py  POST /visual/v2/video
  8  DICOM export                               vision_engine_v2.py  POST /visual/v2/dicom-export
  9  Image similarity search                    vision_engine_v2.py  POST /visual/v2/similar
  10 Score calibration                          vision_engine_v2.py  POST /visual/v2/calibrate-scores
"""

# ─── main.py additions ────────────────────────────────────────────────────────

MAIN_PY = """
from app.api.vision_engine_v2 import router as vision_v2_router
from app.api.vision_landmarks  import router as landmark_router

app.include_router(vision_v2_router)
app.include_router(landmark_router)
"""

# ─── server/routes.ts additions ──────────────────────────────────────────────

ROUTES_TS = """
  // Vision Engine v2 (improvements 1–3, 5, 7–10)
  app.post("/api/visual/v2/analyse",
      (req,res)=>proxyToFastAPI(req,res,"/visual/v2/analyse"));
  app.post("/api/visual/v2/stream", async (req, res) => {
    // SSE proxy — must forward as stream
    res.setHeader("Content-Type","text/event-stream");
    res.setHeader("Cache-Control","no-cache");
    res.setHeader("X-Accel-Buffering","no");
    const formData = ...; // forward multipart/form-data
    const upstream = await fetch(`${PYTHON_API_BASE}/visual/v2/stream`, {
      method: "POST", body: formData, headers: { ...formData.getHeaders() }
    });
    upstream.body.pipe(res);
  });
  app.post("/api/visual/v2/multi-analyse",
      (req,res)=>proxyToFastAPI(req,res,"/visual/v2/multi-analyse"));
  app.post("/api/visual/v2/video",
      (req,res)=>proxyToFastAPI(req,res,"/visual/v2/video"));
  app.post("/api/visual/v2/dicom-export",
      (req,res)=>proxyToFastAPI(req,res,"/visual/v2/dicom-export"));
  app.post("/api/visual/v2/similar",
      (req,res)=>proxyToFastAPI(req,res,"/visual/v2/similar"));
  app.post("/api/visual/v2/index-case",
      (req,res)=>proxyToFastAPI(req,res,"/visual/v2/index-case"));
  app.post("/api/visual/v2/calibrate-scores",
      (req,res)=>proxyToFastAPI(req,res,"/visual/v2/calibrate-scores"));
  app.get ("/api/visual/v2/calibration-table",
      (req,res)=>proxyToFastAPI(req,res,"/visual/v2/calibration-table"));

  // Landmark detection (improvement 4)
  app.post("/api/visual/landmark-analyse",
      (req,res)=>proxyToFastAPI(req,res,"/visual/landmark-analyse"));
  app.post("/api/visual/landmark-preview",
      (req,res)=>proxyToFastAPI(req,res,"/visual/landmark-preview"));
"""

# ─── requirements.txt additions ──────────────────────────────────────────────

REQUIREMENTS = """
# Vision Engine v2 dependencies
anthropic>=0.40.0               # improvement 1: Claude 3.7 routing
pydicom>=2.4.0                  # improvement 8: DICOM export
opencv-python-headless>=4.9.0   # improvements 4,7: landmarks + video
sentence-transformers>=3.0.0    # improvement 9: CLIP embeddings
# Pillow and httpx already in requirements
"""

# ─── Environment variables ────────────────────────────────────────────────────

ENV_VARS = """
# Improvement 1: Vision model routing
VISION_MODEL=gpt-4o                          # default
# VISION_MODEL=claude-sonnet-4-20250514      # switch to Claude 3.7
ANTHROPIC_API_KEY=sk-ant-...                 # required for Claude 3.7

# Improvement 6: PWA base URL
APP_BASE_URL=https://aestheticite.com
"""

# ─── client/src/main.tsx: register service worker ────────────────────────────

SW_REGISTRATION = """
// Add to client/src/main.tsx (after ReactDOM.createRoot):
if ('serviceWorker' in navigator) {
  navigator.serviceWorker
    .register('/vision-sw.js', { scope: '/visual-counsel' })
    .then(reg => {
      console.log('[PWA] Vision service worker registered', reg.scope);
      // Enable periodic background sync if available
      if ('periodicSync' in reg) {
        reg.periodicSync.register('vision-queue-replay', { minInterval: 30000 });
      }
    })
    .catch(err => console.warn('[PWA] SW registration failed:', err));
}
"""

# ─── VisionStreamingAnalysis.tsx extraction ──────────────────────────────────

TSX_NOTE = """
The VisionStreamingAnalysis React component is embedded in vision-sw.js
between the /* === ... === */ block comments.

To extract:
  1. Open vision-sw.js
  2. Copy everything between the /* PASTE BELOW */ and closing */ markers
  3. Save as: client/src/components/vision/VisionStreamingAnalysis.tsx

Then use in ConsultationFlow.tsx Step 2 (analyse):
  import { VisionStreamingAnalysis } from "./VisionStreamingAnalysis";

  <VisionStreamingAnalysis
    file={capturedFiles.front}
    token={token}
    question="Assess this image for post-injectable complication signals."
    onDone={({ fullText, scores, protocols }) => {
      setAnalysisText(fullText);
      setVisualScores(scores);
      setTriggeredProtocols(protocols);
      advance("signals");
    }}
  />

This replaces the current blocking fetch in runAnalysis().
"""

# ─── Per-improvement activation checklist ────────────────────────────────────

CHECKLIST = {
    1:  "Set VISION_MODEL=claude-sonnet-4-20250514 + ANTHROPIC_API_KEY to activate Claude 3.7",
    2:  "Add /api/visual/v2/stream SSE proxy to routes.ts; replace ConsultationFlow.runAnalysis() with VisionStreamingAnalysis",
    3:  "Add /api/visual/v2/multi-analyse route; call from ConsultationFlow serial comparison step",
    4:  "Add vision_landmarks router to main.py; add /api/visual/landmark-analyse route; pip install opencv-python-headless",
    5:  "Automatic — preprocess_image() is called inside /v2/analyse and /v2/stream. No config needed.",
    6:  "Copy vision-sw.js to public/; add SW registration to main.tsx",
    7:  "Add /api/visual/v2/video route; pip install opencv-python-headless (shared with improvement 4)",
    8:  "Add /api/visual/v2/dicom-export route; pip install pydicom",
    9:  "Add /api/visual/v2/similar and /v2/index-case routes; pip install sentence-transformers; call /v2/index-case after every session auto-log",
    10: "Add /api/visual/v2/calibrate-scores route; run calibration once you have 50+ confirmed training cases",
}

if __name__ == "__main__":
    print("AesthetiCite Vision — 10 Technical Improvements")
    print("=" * 50)
    for n, desc in CHECKLIST.items():
        print(f"  {n:2d}. {desc}")
