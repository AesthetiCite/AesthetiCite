/**
 * AesthetiCite Vision — Integration
 * vision-integration.ts
 *
 * Three changes to wire the new feature into the existing app.
 * All are additions — nothing existing is removed or replaced.
 */


// ═══════════════════════════════════════════════════════════════════════════
// 1. app/main.py — add router
// ═══════════════════════════════════════════════════════════════════════════
//
// ADD this import alongside the existing router imports:
//
//   from app.api.vision_followup import router as vision_router
//
// ADD this include alongside the existing includes (after visual_counseling_router):
//
//   app.include_router(vision_router)


// ═══════════════════════════════════════════════════════════════════════════
// 2. server/routes.ts — add Express proxy
// ═══════════════════════════════════════════════════════════════════════════
//
// ADD these lines alongside the existing visual counseling routes
// (after the /api/visual/* routes, before the voice routes):
//
//   // AesthetiCite Vision — serial image analysis
//   app.all(["/api/vision", "/api/vision/*splat"], (req: Request, res: Response) => {
//     proxyToFastAPI(req, res, req.path);
//   });
//
// NOTE: The /api/vision/analyze endpoint uses multipart/form-data with multiple
// files. The existing proxyToFastAPI uses JSON.stringify(req.body) for non-GET
// requests, which will NOT work for file uploads.
//
// Use this dedicated vision proxy instead:

export const VISION_PROXY_CODE = `
  // AesthetiCite Vision proxy — handles multipart file uploads
  app.post("/api/vision/analyze", upload.array("files", 10), async (req: Request, res: Response) => {
    try {
      const files = req.files as Express.Multer.File[];
      if (!files || files.length === 0) {
        return res.status(400).json({ detail: "No image files provided" });
      }

      const FormDataLib = require("form-data");
      const form = new FormDataLib();
      form.append("procedure", req.body.procedure || "injectables");
      form.append("notes", req.body.notes || "");
      for (const file of files) {
        form.append("files", file.buffer, {
          filename: file.originalname || "image.jpg",
          contentType: file.mimetype,
        });
      }

      const response = await fetch(\`\${PYTHON_API_BASE}/api/vision/analyze\`, {
        method: "POST",
        headers: {
          ...form.getHeaders(),
          ...(req.headers.authorization ? { Authorization: req.headers.authorization as string } : {}),
        },
        body: form,
      });
      const text = await response.text();
      let data: any;
      try { data = JSON.parse(text); } catch { data = { detail: text.slice(0, 400) }; }
      res.status(response.status).json(data);
    } catch (error) {
      console.error("Vision analyze error:", error);
      res.status(502).json({ detail: "Vision analysis service unavailable" });
    }
  });

  app.post("/api/vision/analyze/export", upload.array("files", 10), async (req: Request, res: Response) => {
    try {
      const files = req.files as Express.Multer.File[];
      if (!files || files.length === 0) {
        return res.status(400).json({ detail: "No image files provided" });
      }

      const FormDataLib = require("form-data");
      const form = new FormDataLib();
      form.append("procedure", req.body.procedure || "injectables");
      form.append("notes", req.body.notes || "");
      for (const file of files) {
        form.append("files", file.buffer, {
          filename: file.originalname || "image.jpg",
          contentType: file.mimetype,
        });
      }

      const response = await fetch(\`\${PYTHON_API_BASE}/api/vision/analyze/export\`, {
        method: "POST",
        headers: {
          ...form.getHeaders(),
          ...(req.headers.authorization ? { Authorization: req.headers.authorization as string } : {}),
        },
        body: form,
      });
      const data = await response.json();
      res.status(response.status).json(data);
    } catch (error) {
      console.error("Vision export error:", error);
      res.status(502).json({ detail: "Vision export service unavailable" });
    }
  });

  app.get("/api/vision/procedures", (req: Request, res: Response) => {
    proxyToFastAPI(req, res, "/api/vision/procedures");
  });
`;


// ═══════════════════════════════════════════════════════════════════════════
// 3. client/src/App.tsx — add route
// ═══════════════════════════════════════════════════════════════════════════
//
// ADD this import:
//   import VisionFollowupPage from "@/pages/vision-followup";
//
// ADD this route in Router() alongside the other protected routes:
//   <Route path="/vision-followup">
//     {() => <ProtectedRoute component={VisionFollowupPage} />}
//   </Route>


// ═══════════════════════════════════════════════════════════════════════════
// 4. Sidebar — add to mobile Sheet and More dropdown
// ═══════════════════════════════════════════════════════════════════════════
//
// In the mobile Sheet nav under "Safety & Tools", add:
//   <Link href="/vision-followup" className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-muted transition-colors">
//     <Camera className="h-4 w-4" />AesthetiCite Vision
//   </Link>
//
// In the More dropdown under Clinical:
//   <DropdownMenuItem asChild>
//     <Link href="/vision-followup" className="flex items-center gap-2 cursor-pointer">
//       <Camera className="h-4 w-4 text-muted-foreground" />Vision Follow-up
//     </Link>
//   </DropdownMenuItem>
//
// In sidebar-safety-nav.tsx, optionally add as a 4th entry under Clinical Tools:
// (Camera icon is already in lucide-react)


// ═══════════════════════════════════════════════════════════════════════════
// 5. Python dependencies — add to requirements.txt if not present
// ═══════════════════════════════════════════════════════════════════════════
//
//   opencv-python-headless   # lighter than opencv-python, no GUI dependency
//   Pillow                   # already installed
//   numpy                    # already installed
//   reportlab                # already installed
//
// If opencv-python is already installed, do not add opencv-python-headless.
// They conflict. Check with: pip show opencv-python


// ═══════════════════════════════════════════════════════════════════════════
// Summary
// ═══════════════════════════════════════════════════════════════════════════
//
// After these changes, AesthetiCite Vision is available at /vision-followup.
//
// What it provides (vs the existing visual counseling feature):
//
//   Existing /visual-counsel:
//     - Single photo upload
//     - Evidence-grounded Q&A via streaming LLM
//     - Counseling about treatment scenarios
//
//   New /vision-followup (AesthetiCite Vision):
//     - Serial photo upload (2–10 images)
//     - Automated timeline sorting by filename
//     - Per-image asymmetry, redness, brightness metrics
//     - Baseline vs latest slider comparison
//     - Healing trend classification
//     - Urgency flagging (Routine / Review / Urgent / Emergency)
//     - Complication pattern detection (blanching, visual symptoms, infection)
//     - Reportlab PDF export
//     - All CPU work in asyncio.to_thread — event loop never blocked
//     - Auth required
//     - Image quality validation (blank, overexposed, zero contrast)
//     - 20MB per image limit
//     - Accurate metric naming (brightness_proxy, not swelling_proxy)
//     - Explicit positioning caveat on all metric outputs

export {};
