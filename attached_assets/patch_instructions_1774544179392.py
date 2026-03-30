"""
PATCH INSTRUCTIONS
==================
Three files need changes. Each section shows exactly what to find
and what to replace it with. Nothing else in those files changes.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILE 1: app/api/complication_protocol_engine.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CHANGE 1 — Add import at the top (after existing imports):

    from app.api.case_store import log_case, get_stats, list_cases


CHANGE 2 — Remove this line (the in-memory store declaration):

    CASE_STORE: List[LoggedCase] = []


CHANGE 3 — Replace the /log-case endpoint body.

FIND:
    @router.post("/log-case", response_model=LogCaseResponse)
    def log_case_endpoint(payload: LogCaseRequest) -> LogCaseResponse:
        if payload.protocol_key not in PROTOCOL_LIBRARY:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown protocol_key: {payload.protocol_key}. "
                       f"Valid keys: {list(PROTOCOL_LIBRARY.keys())}",
            )
        case_id = str(uuid.uuid4())
        case = LoggedCase(
            case_id=case_id,
            logged_at_utc=now_utc_iso(),
            clinic_id=payload.clinic_id,
            clinician_id=payload.clinician_id,
            protocol_key=payload.protocol_key,
            region=payload.region,
            procedure=payload.procedure,
            product_type=payload.product_type,
            symptoms=payload.symptoms,
            outcome=payload.outcome,
        )
        CASE_STORE.append(case)
        safe_write_jsonl(AUDIT_LOG_PATH, {
            "event_type": "case_logged",
            "logged_at_utc": case.logged_at_utc,
            "case_id": case_id,
            "clinic_id": payload.clinic_id,
            "clinician_id": payload.clinician_id,
            "protocol_key": payload.protocol_key,
            "region": payload.region,
            "procedure": payload.procedure,
            "outcome": payload.outcome,
        })
        return LogCaseResponse(status="ok", case_id=case_id)

REPLACE WITH:
    @router.post("/log-case", response_model=LogCaseResponse)
    def log_case_endpoint(payload: LogCaseRequest) -> LogCaseResponse:
        if payload.protocol_key not in PROTOCOL_LIBRARY:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown protocol_key: {payload.protocol_key}. "
                       f"Valid keys: {list(PROTOCOL_LIBRARY.keys())}",
            )
        case_id = log_case(
            protocol_key=payload.protocol_key,
            clinic_id=payload.clinic_id,
            clinician_id=payload.clinician_id,
            region=payload.region,
            procedure=payload.procedure,
            product_type=payload.product_type,
            symptoms=payload.symptoms,
            outcome=payload.outcome,
        )
        safe_write_jsonl(AUDIT_LOG_PATH, {
            "event_type": "case_logged",
            "logged_at_utc": now_utc_iso(),
            "case_id": case_id,
            "protocol_key": payload.protocol_key,
            "clinic_id": payload.clinic_id,
            "clinician_id": payload.clinician_id,
            "region": payload.region,
            "procedure": payload.procedure,
            "outcome": payload.outcome,
        })
        return LogCaseResponse(status="ok", case_id=case_id)


CHANGE 4 — Replace the /stats endpoint body.

FIND:
    @router.get("/stats", response_model=DatasetStatsResponse)
    def dataset_stats() -> DatasetStatsResponse:
        return DatasetStatsResponse(
            total_cases=len(CASE_STORE),
            by_protocol=dict(Counter(c.protocol_key for c in CASE_STORE if c.protocol_key)),
            by_region=dict(Counter(c.region for c in CASE_STORE if c.region)),
            by_procedure=dict(Counter(c.procedure for c in CASE_STORE if c.procedure)),
        )

REPLACE WITH:
    @router.get("/stats", response_model=DatasetStatsResponse)
    def dataset_stats() -> DatasetStatsResponse:
        return DatasetStatsResponse(**get_stats())


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILE 2: app/api/visual_counseling.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Replace the entire file with visual_counseling_fixed.py.
(The new file is a complete drop-in — same router prefix, same
endpoints, same response shapes. Only the storage layer changes.)


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILE 3: app/main.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CHANGE 1 — Add import near the top with other startup imports:

    from app.api.case_store import create_table_sync


CHANGE 2 — Add one line in the startup section, after ensure_users_table():

    ensure_users_table()
    create_table_sync()   # <-- add this line


That is the complete set of changes.
After applying:
- Logged cases persist to Postgres across restarts
- Uploaded images persist to disk across restarts
- No data loss on server restart or redeploy
"""
