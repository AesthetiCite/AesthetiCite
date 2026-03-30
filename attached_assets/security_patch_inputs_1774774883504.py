"""
security_patch_inputs.py
=========================
THREE files to patch:
  FILE A — app/api/vision_analysis.py
  FILE B — app/api/clinical_tools_engine.py
  FILE C — app/api/visual_counseling.py  (file upload validation)

Plus rate limits on vision endpoints (already in vision_analysis.py template
but adding them here for clarity).

═══════════════════════════════════════════════════════════════════
FILE A — app/api/vision_analysis.py

STEP 1: Add import at top of file:
    from app.core.safety import sanitize_input
    from fastapi import Request

STEP 2: Add rate limit decorators (add @limiter.limit before each endpoint):

    Find:
        @router.post("/analyse", response_model=VisionResponse)
        def vision_analyse(req: VisionRequest) -> VisionResponse:

    Replace with:
        @router.post("/analyse", response_model=VisionResponse)
        @limiter.limit("10/minute;50/hour")
        def vision_analyse(request: Request, req: VisionRequest) -> VisionResponse:


    Find:
        @router.post("/serial-compare", response_model=SerialResult)
        def serial_compare(req: SerialRequest) -> SerialResult:

    Replace with:
        @router.post("/serial-compare", response_model=SerialResult)
        @limiter.limit("5/minute;20/hour")
        def serial_compare(request: Request, req: SerialRequest) -> SerialResult:


STEP 3: At the top of vision_analyse(), BEFORE the _load() call, add:

    # Sanitise all free-text fields
    if req.procedure_type:
        req.procedure_type = sanitize_input(req.procedure_type)
    if req.injected_region:
        req.injected_region = sanitize_input(req.injected_region)
    if req.product_type:
        req.product_type = sanitize_input(req.product_type)
    if req.clinical_notes:
        req.clinical_notes = sanitize_input(req.clinical_notes)
    if req.patient_symptoms:
        req.patient_symptoms = [
            sanitize_input(s) for s in req.patient_symptoms if s
        ]

Also add to serial_compare():
    if req.procedure_type:
        req.procedure_type = sanitize_input(req.procedure_type)
    if req.clinical_notes:
        req.clinical_notes = sanitize_input(req.clinical_notes)

Also add these imports at the top of vision_analysis.py:
    from app.core.limiter import limiter


═══════════════════════════════════════════════════════════════════
FILE B — app/api/clinical_tools_engine.py

STEP 1: Add imports at top:
    from app.core.safety import sanitize_input
    from app.core.limiter import limiter
    from fastapi import Request

STEP 2: Add rate limit + sanitise to each AI endpoint.
        (The pure-calculation tools don't need rate limits — only the 5
         LLM-calling endpoints.)

    Find:
        @router.post("/glp1-assessment")
        def glp1_assessment(req: GLP1Request):

    Replace with:
        @router.post("/glp1-assessment")
        @limiter.limit("20/minute")
        def glp1_assessment(request: Request, req: GLP1Request):
            if req.planned_treatment:
                req.planned_treatment = sanitize_input(req.planned_treatment)
            if req.current_dose:
                req.current_dose = sanitize_input(req.current_dose)


    Find:
        @router.post("/vascular-risk")
        def vascular_risk(req: VascularRiskRequest):

    Replace with:
        @router.post("/vascular-risk")
        @limiter.limit("20/minute")
        def vascular_risk(request: Request, req: VascularRiskRequest):
            req.region    = sanitize_input(req.region)
            req.product   = sanitize_input(req.product)
            req.technique = sanitize_input(req.technique)
            req.layer     = sanitize_input(req.layer)


    Find:
        @router.post("/consent-checklist")
        def consent_checklist(req: ConsentRequest):

    Replace with:
        @router.post("/consent-checklist")
        @limiter.limit("10/minute;30/hour")
        def consent_checklist(request: Request, req: ConsentRequest):
            req.treatment = sanitize_input(req.treatment)
            if req.patient_factors:
                req.patient_factors = [sanitize_input(f) for f in req.patient_factors]


    Find:
        @router.post("/aftercare")
        def aftercare_sheet(req: AftercareRequest):

    Replace with:
        @router.post("/aftercare")
        @limiter.limit("20/minute")
        def aftercare_sheet(request: Request, req: AftercareRequest):
            req.treatment = sanitize_input(req.treatment)
            if req.region:
                req.region = sanitize_input(req.region)
            if req.patient_factors:
                req.patient_factors = [sanitize_input(f) for f in req.patient_factors]


    Find:
        @router.post("/toxin-dosing")
        def toxin_dosing(req: ToxinDosingRequest):

    Replace with:
        @router.post("/toxin-dosing")
        @limiter.limit("20/minute")
        def toxin_dosing(request: Request, req: ToxinDosingRequest):
            req.region       = sanitize_input(req.region)
            req.product      = sanitize_input(req.product)
            req.patient_type = sanitize_input(req.patient_type)


═══════════════════════════════════════════════════════════════════
FILE C — app/api/visual_counseling.py  (file upload security)

STEP 1: Add to requirements.txt:
    python-magic>=0.4.27

    Then install:
    pip install python-magic

    NOTE: On Linux (Railway/Replit), also needs:
    apt-get install libmagic1  (or it's usually already installed)
    If libmagic is not available, use the fallback approach below.

STEP 2: Add imports at top of visual_counseling.py:
    import magic   # python-magic — server-side MIME detection

STEP 3: Find the upload endpoint. It looks something like:

    @router.post("/visual/upload")
    async def upload_visual(
        file: UploadFile,
        conversation_id: str = Form(...),
        kind: str = Form("photo"),
        ...
    ):
        contents = await file.read()
        ...

    Add these validation lines IMMEDIATELY after contents = await file.read():

        # ── File size limit ──────────────────────────────────────
        MAX_BYTES = 20 * 1024 * 1024  # 20 MB
        if len(contents) > MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File too large ({len(contents) // (1024*1024)} MB). Maximum 20 MB.",
            )

        # ── MIME type validation (server-side) ───────────────────
        ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}
        try:
            mime_type = magic.from_buffer(contents[:2048], mime=True)
        except Exception:
            # Fallback: check file header bytes if libmagic unavailable
            mime_type = _detect_mime_fallback(contents)

        if mime_type not in ALLOWED_MIME:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported file type: {mime_type}. Please upload JPEG, PNG, or WEBP.",
            )

        # ── Filename sanitisation ────────────────────────────────
        safe_filename = re.sub(r"[^a-zA-Z0-9._-]", "_", file.filename or "upload")
        safe_filename = safe_filename[:100]  # truncate long filenames

STEP 4: Add the fallback MIME detector function to visual_counseling.py
        (add before the router definition):

    def _detect_mime_fallback(data: bytes) -> str:
        \"\"\"Simple magic byte check — fallback when libmagic is unavailable.\"\"\"
        if data[:3] == b'\\xff\\xd8\\xff':
            return "image/jpeg"
        if data[:8] == b'\\x89PNG\\r\\n\\x1a\\n':
            return "image/png"
        if data[:4] in (b'RIFF',) and data[8:12] == b'WEBP':
            return "image/webp"
        if data[:6] in (b'GIF87a', b'GIF89a'):
            return "image/gif"
        return "application/octet-stream"  # unknown — will be rejected


═══════════════════════════════════════════════════════════════════
FILE D — app/api/complication_protocol_engine.py

STEP 1: Add import:
    from app.core.safety import sanitize_input

STEP 2: At the top of generate_protocol():

    Find:
        def generate_protocol(payload: ProtocolRequest) -> ProtocolResponse:
            request_id = str(uuid.uuid4())

    Add after the first line:
            # Sanitise all user-supplied text
            payload.query = sanitize_input(payload.query)
            if payload.context and payload.context.clinical_context:
                payload.context.clinical_context = sanitize_input(
                    payload.context.clinical_context
                )


═══════════════════════════════════════════════════════════════════
FILE E — app/api/preprocedure_safety_engine.py

STEP 1: Add import:
    from app.core.safety import sanitize_input

STEP 2: At the top of the check endpoint handler, add:

    request.procedure     = sanitize_input(request.procedure)
    request.region        = sanitize_input(request.region or "")
    request.product_type  = sanitize_input(request.product_type or "")
    if request.technique:
        request.technique = sanitize_input(request.technique)
    if request.patient_factors and hasattr(request.patient_factors, 'notes'):
        if request.patient_factors.notes:
            request.patient_factors.notes = sanitize_input(
                request.patient_factors.notes
            )
"""
