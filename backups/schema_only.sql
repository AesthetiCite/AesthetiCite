--
-- PostgreSQL database dump
--

-- Dumped from database version 16.10
-- Dumped by pg_dump version 16.3

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: drizzle; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA drizzle;


--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: __drizzle_migrations; Type: TABLE; Schema: drizzle; Owner: -
--

CREATE TABLE drizzle.__drizzle_migrations (
    id integer NOT NULL,
    hash text NOT NULL,
    created_at bigint
);


--
-- Name: __drizzle_migrations_id_seq; Type: SEQUENCE; Schema: drizzle; Owner: -
--

CREATE SEQUENCE drizzle.__drizzle_migrations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: __drizzle_migrations_id_seq; Type: SEQUENCE OWNED BY; Schema: drizzle; Owner: -
--

ALTER SEQUENCE drizzle.__drizzle_migrations_id_seq OWNED BY drizzle.__drizzle_migrations.id;


--
-- Name: __drizzle_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.__drizzle_migrations (
    id integer NOT NULL,
    hash text NOT NULL,
    created_at bigint
);


--
-- Name: __drizzle_migrations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.__drizzle_migrations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: __drizzle_migrations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.__drizzle_migrations_id_seq OWNED BY public.__drizzle_migrations.id;


--
-- Name: analytics_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.analytics_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    org_id uuid,
    clinic_id uuid,
    user_id uuid,
    event_type text NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: answers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.answers (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    query_id uuid NOT NULL,
    answer_text text NOT NULL,
    citations_json jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: auth_access_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.auth_access_requests (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    email text NOT NULL,
    token text NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: auth_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.auth_tokens (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    token_hash text NOT NULL,
    token_type text NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT auth_tokens_token_type_check CHECK ((token_type = ANY (ARRAY['password_reset'::text, 'email_verify'::text])))
);


--
-- Name: case_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.case_logs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    org_id uuid,
    clinic_id uuid,
    created_by uuid NOT NULL,
    patient_reference text NOT NULL,
    event_date timestamp with time zone,
    practitioner_name text,
    procedure text,
    region text,
    product_used text,
    complication_type text,
    symptoms text,
    suspected_diagnosis text,
    treatment_given text,
    hyaluronidase_dose text,
    follow_up_plan text,
    outcome text,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: chunks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chunks (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    document_id uuid NOT NULL,
    chunk_index integer NOT NULL,
    text text NOT NULL,
    page_or_section text,
    evidence_level text,
    embedding public.vector(384),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    tsv tsvector GENERATED ALWAYS AS (to_tsvector('english'::regconfig, COALESCE(text, ''::text))) STORED,
    text_norm text GENERATED ALWAYS AS (lower(regexp_replace(COALESCE(text, ''::text), '\s+'::text, ' '::text, 'g'::text))) STORED
)
WITH (autovacuum_enabled='false');


--
-- Name: clinician_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.clinician_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    org_id uuid,
    clinic_id uuid,
    user_id uuid,
    session_id text,
    event_type text NOT NULL,
    target_element text,
    answer_section text,
    query_id text,
    duration_ms integer,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: clinics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.clinics (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    org_id uuid NOT NULL,
    name text NOT NULL,
    address text,
    timezone text DEFAULT 'UTC'::text NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: complication_alerts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.complication_alerts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    org_id uuid NOT NULL,
    clinic_id uuid NOT NULL,
    alert_type text NOT NULL,
    severity text NOT NULL,
    title text NOT NULL,
    body text NOT NULL,
    evidence_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    is_dismissed boolean DEFAULT false NOT NULL,
    dismissed_by uuid,
    dismissed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT complication_alerts_severity_check CHECK ((severity = ANY (ARRAY['info'::text, 'warning'::text, 'critical'::text])))
);


--
-- Name: complication_cases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.complication_cases (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id text,
    clinician_id text,
    protocol_key text,
    region text,
    procedure text,
    product_type text,
    symptoms jsonb DEFAULT '[]'::jsonb,
    outcome text,
    notes text,
    engine_response jsonb DEFAULT '{}'::jsonb,
    logged_at_utc timestamp with time zone DEFAULT now()
);


--
-- Name: complication_monitors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.complication_monitors (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    org_id uuid NOT NULL,
    clinic_id uuid NOT NULL,
    case_log_id uuid,
    created_by uuid NOT NULL,
    patient_reference text NOT NULL,
    procedure text,
    region text,
    monitor_status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT complication_monitors_monitor_status_check CHECK ((monitor_status = ANY (ARRAY['active'::text, 'resolved'::text, 'escalated'::text, 'closed'::text])))
);


--
-- Name: conversations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.conversations (
    id text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    user_id text,
    title text
);


--
-- Name: documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.documents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    source_id text NOT NULL,
    title text NOT NULL,
    authors text,
    organization_or_journal text,
    year integer,
    document_type text NOT NULL,
    domain text NOT NULL,
    version text,
    status text DEFAULT 'active'::text NOT NULL,
    url text,
    file_path text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    language text DEFAULT 'en'::text,
    abstract text,
    journal text,
    specialty text
)
WITH (autovacuum_enabled='false');


--
-- Name: documents_meta; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.documents_meta (
    source_id text NOT NULL,
    doi text,
    pmid text,
    url text,
    title text,
    journal text,
    year integer,
    publication_type text,
    source_tier text,
    evidence_type text,
    evidence_rank integer,
    organization text,
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: dosing_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dosing_rules (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    category text NOT NULL,
    rule_json jsonb NOT NULL,
    source_id text,
    source_excerpt text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: growth_api_keys; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.growth_api_keys (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id text NOT NULL,
    label text NOT NULL,
    key_hash text NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: growth_bookmarks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.growth_bookmarks (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id text NOT NULL,
    title text NOT NULL,
    question text NOT NULL,
    answer_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    tags jsonb DEFAULT '[]'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: growth_knowledge_chunks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.growth_knowledge_chunks (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    title text NOT NULL,
    content text NOT NULL,
    source_type text,
    source_ref text,
    tags jsonb DEFAULT '[]'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: growth_paper_alert_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.growth_paper_alert_items (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    subscription_id uuid NOT NULL,
    paper_title text NOT NULL,
    paper_abstract text,
    source_url text,
    published_date text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: growth_paper_subscriptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.growth_paper_subscriptions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id text NOT NULL,
    topic text NOT NULL,
    email text,
    last_checked_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: growth_patient_exports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.growth_patient_exports (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id text,
    clinician_id text,
    source_title text NOT NULL,
    source_text text NOT NULL,
    patient_text text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: growth_query_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.growth_query_logs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id text,
    clinician_id text,
    query_text text NOT NULL,
    answer_type text,
    aci_score real,
    response_time_ms real,
    evidence_level text,
    domain text DEFAULT 'aesthetic_medicine'::text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: growth_session_report_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.growth_session_report_items (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    report_id uuid NOT NULL,
    patient_label text,
    procedure text NOT NULL,
    region text NOT NULL,
    product_type text NOT NULL,
    technique text,
    injector_experience_level text,
    engine_response jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: growth_session_reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.growth_session_reports (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    clinic_id text,
    clinician_id text,
    title text NOT NULL,
    report_date date,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: ingestion_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ingestion_runs (
    run_id integer NOT NULL,
    started_at timestamp with time zone DEFAULT now(),
    ended_at timestamp with time zone,
    mode character varying(50) NOT NULL,
    query_plan_hash character varying(64),
    config_snapshot jsonb,
    pmids_found integer DEFAULT 0,
    pmids_fetched integer DEFAULT 0,
    pmids_stored integer DEFAULT 0,
    pmids_skipped integer DEFAULT 0,
    pmids_failed integer DEFAULT 0,
    errors jsonb DEFAULT '[]'::jsonb,
    status character varying(20) DEFAULT 'running'::character varying
);


--
-- Name: ingestion_runs_run_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ingestion_runs_run_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ingestion_runs_run_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ingestion_runs_run_id_seq OWNED BY public.ingestion_runs.run_id;


--
-- Name: llm_provider_configs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.llm_provider_configs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    org_id uuid NOT NULL,
    provider text DEFAULT 'openai'::text NOT NULL,
    model text DEFAULT 'gpt-4o'::text NOT NULL,
    api_key_enc text,
    base_url text,
    on_premise boolean DEFAULT false NOT NULL,
    extra_params jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT llm_provider_configs_provider_check CHECK ((provider = ANY (ARRAY['openai'::text, 'mistral'::text, 'azure_openai'::text, 'local'::text])))
);


--
-- Name: memberships; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.memberships (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    clinic_id uuid NOT NULL,
    org_id uuid NOT NULL,
    role text DEFAULT 'clinician'::text NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.messages (
    id bigint NOT NULL,
    conversation_id text NOT NULL,
    role text NOT NULL,
    content text NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: messages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.messages_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.messages_id_seq OWNED BY public.messages.id;


--
-- Name: monitor_submissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.monitor_submissions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    monitor_id uuid NOT NULL,
    submitted_by uuid,
    image_url text,
    image_b64 text,
    notes text,
    ai_assessment jsonb DEFAULT '{}'::jsonb NOT NULL,
    alert_triggered boolean DEFAULT false NOT NULL,
    submitted_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: network_case_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.network_case_logs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    org_id uuid,
    clinic_id uuid,
    created_by uuid,
    patient_reference text,
    incident_at timestamp with time zone DEFAULT now() NOT NULL,
    practitioner_name text,
    procedure text,
    region text,
    product text,
    complication_type text,
    symptoms text,
    suspected_diagnosis text,
    treatment_given text,
    hyaluronidase_dose text,
    follow_up_plan text,
    outcome text,
    notes text,
    evidence_snapshot jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: organizations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organizations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    slug text NOT NULL,
    plan text DEFAULT 'starter'::text NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: pilot_cases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pilot_cases (
    case_id text NOT NULL,
    site_id text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    closed_at timestamp with time zone,
    phase text DEFAULT 'aestheticite'::text NOT NULL,
    case_ref text,
    procedure text,
    area text,
    suspected_complication text,
    notes text
);


--
-- Name: pilot_documentation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pilot_documentation (
    doc_id text NOT NULL,
    case_id text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    mode text DEFAULT 'aestheticite'::text NOT NULL,
    fields_json jsonb NOT NULL,
    generated_note text
);


--
-- Name: pilot_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pilot_events (
    event_id text NOT NULL,
    case_id text NOT NULL,
    event_type text NOT NULL,
    event_ts timestamp with time zone NOT NULL,
    payload jsonb,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: pilot_sites; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pilot_sites (
    site_id text NOT NULL,
    site_name text NOT NULL,
    country text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: pilot_users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pilot_users (
    user_id text NOT NULL,
    site_id text NOT NULL,
    email text,
    role text DEFAULT 'clinician'::text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: pipeline_checkpoints; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pipeline_checkpoints (
    checkpoint_id integer NOT NULL,
    run_id integer,
    stage character varying(50),
    batch_number integer,
    last_pmid character varying(20),
    checkpoint_data jsonb,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: pipeline_checkpoints_checkpoint_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pipeline_checkpoints_checkpoint_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pipeline_checkpoints_checkpoint_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pipeline_checkpoints_checkpoint_id_seq OWNED BY public.pipeline_checkpoints.checkpoint_id;


--
-- Name: pmc_fulltext; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pmc_fulltext (
    pmc_id character varying(20) NOT NULL,
    pmid character varying(20),
    full_text text,
    sections jsonb,
    license character varying(100),
    fetched_at timestamp with time zone DEFAULT now()
);


--
-- Name: pmid_queue; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pmid_queue (
    id integer NOT NULL,
    run_id integer,
    pmid character varying(20) NOT NULL,
    tier character varying(20),
    query_group character varying(100),
    status character varying(20) DEFAULT 'pending'::character varying,
    attempts integer DEFAULT 0,
    last_error text,
    created_at timestamp with time zone DEFAULT now(),
    processed_at timestamp with time zone
);


--
-- Name: pmid_queue_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pmid_queue_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pmid_queue_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pmid_queue_id_seq OWNED BY public.pmid_queue.id;


--
-- Name: practitioner_risk_scores; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.practitioner_risk_scores (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    org_id uuid NOT NULL,
    clinic_id uuid NOT NULL,
    practitioner_name text NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    total_cases integer DEFAULT 0 NOT NULL,
    high_risk_cases integer DEFAULT 0 NOT NULL,
    vascular_cases integer DEFAULT 0 NOT NULL,
    necrosis_cases integer DEFAULT 0 NOT NULL,
    visual_cases integer DEFAULT 0 NOT NULL,
    unresolved_cases integer DEFAULT 0 NOT NULL,
    risk_score numeric(5,2) DEFAULT 0 NOT NULL,
    risk_level text DEFAULT 'normal'::text NOT NULL,
    top_complications jsonb DEFAULT '[]'::jsonb NOT NULL,
    generated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT practitioner_risk_scores_risk_level_check CHECK ((risk_level = ANY (ARRAY['normal'::text, 'elevated'::text, 'high'::text, 'critical'::text])))
);


--
-- Name: publication_syncs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.publication_syncs (
    id integer NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    status text DEFAULT 'running'::text NOT NULL,
    papers_found integer DEFAULT 0,
    papers_downloaded integer DEFAULT 0,
    papers_ingested integer DEFAULT 0,
    papers_skipped integer DEFAULT 0,
    error_message text,
    date_range_start date,
    date_range_end date
);


--
-- Name: publication_syncs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.publication_syncs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: publication_syncs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.publication_syncs_id_seq OWNED BY public.publication_syncs.id;


--
-- Name: publications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.publications (
    pmid character varying(20) NOT NULL,
    title text,
    abstract text,
    journal character varying(500),
    year integer,
    doi character varying(200),
    publication_types text[],
    mesh_terms text[],
    authors text[],
    language character varying(20),
    pmc_id character varying(20),
    pubmed_url character varying(200),
    source character varying(50) DEFAULT 'pubmed'::character varying,
    source_type character varying(50),
    quality_rank integer DEFAULT 50,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: queries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.queries (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id text,
    question text NOT NULL,
    domain text,
    mode text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    latency_ms integer,
    citations_count integer,
    refusal boolean DEFAULT false NOT NULL,
    refusal_reason text
);


--
-- Name: query_logs_v2; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.query_logs_v2 (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id text,
    clinic_id text,
    clinician_id text,
    query_text text NOT NULL,
    answer_type text,
    aci_score real,
    response_time_ms real,
    evidence_level text,
    domain text DEFAULT 'aesthetic_medicine'::text,
    session_id text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: safety_reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.safety_reports (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    org_id uuid,
    clinic_id uuid,
    created_by uuid,
    case_log_id uuid,
    source_type text DEFAULT 'guidance'::text NOT NULL,
    title text NOT NULL,
    report_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: saved_protocols; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.saved_protocols (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    org_id uuid,
    clinic_id uuid,
    created_by uuid,
    title text NOT NULL,
    source_query text,
    answer_json jsonb,
    citations_json jsonb,
    tags text[] DEFAULT '{}'::text[],
    is_approved boolean DEFAULT false NOT NULL,
    is_pinned boolean DEFAULT false NOT NULL,
    is_archived boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: search_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.search_history (
    id integer NOT NULL,
    query character varying(500) NOT NULL,
    answer text,
    embedding public.vector(384),
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: search_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.search_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: search_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.search_history_id_seq OWNED BY public.search_history.id;


--
-- Name: user_interests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_interests (
    user_id text NOT NULL,
    topic text NOT NULL,
    email text,
    created_at integer NOT NULL
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    email text NOT NULL,
    password_hash text NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    role text DEFAULT 'clinician'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    full_name text,
    practitioner_id text,
    clinic_id text,
    email_verified boolean DEFAULT false,
    email_verified_at timestamp with time zone
);


--
-- Name: visuals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.visuals (
    id text NOT NULL,
    user_id text NOT NULL,
    conversation_id text NOT NULL,
    kind text DEFAULT 'photo'::text NOT NULL,
    image_bytes bytea NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: __drizzle_migrations id; Type: DEFAULT; Schema: drizzle; Owner: -
--

ALTER TABLE ONLY drizzle.__drizzle_migrations ALTER COLUMN id SET DEFAULT nextval('drizzle.__drizzle_migrations_id_seq'::regclass);


--
-- Name: __drizzle_migrations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.__drizzle_migrations ALTER COLUMN id SET DEFAULT nextval('public.__drizzle_migrations_id_seq'::regclass);


--
-- Name: ingestion_runs run_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingestion_runs ALTER COLUMN run_id SET DEFAULT nextval('public.ingestion_runs_run_id_seq'::regclass);


--
-- Name: messages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages ALTER COLUMN id SET DEFAULT nextval('public.messages_id_seq'::regclass);


--
-- Name: pipeline_checkpoints checkpoint_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_checkpoints ALTER COLUMN checkpoint_id SET DEFAULT nextval('public.pipeline_checkpoints_checkpoint_id_seq'::regclass);


--
-- Name: pmid_queue id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pmid_queue ALTER COLUMN id SET DEFAULT nextval('public.pmid_queue_id_seq'::regclass);


--
-- Name: publication_syncs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.publication_syncs ALTER COLUMN id SET DEFAULT nextval('public.publication_syncs_id_seq'::regclass);


--
-- Name: search_history id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.search_history ALTER COLUMN id SET DEFAULT nextval('public.search_history_id_seq'::regclass);


--
-- Name: __drizzle_migrations __drizzle_migrations_pkey; Type: CONSTRAINT; Schema: drizzle; Owner: -
--

ALTER TABLE ONLY drizzle.__drizzle_migrations
    ADD CONSTRAINT __drizzle_migrations_pkey PRIMARY KEY (id);


--
-- Name: __drizzle_migrations __drizzle_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.__drizzle_migrations
    ADD CONSTRAINT __drizzle_migrations_pkey PRIMARY KEY (id);


--
-- Name: analytics_events analytics_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_events
    ADD CONSTRAINT analytics_events_pkey PRIMARY KEY (id);


--
-- Name: answers answers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.answers
    ADD CONSTRAINT answers_pkey PRIMARY KEY (id);


--
-- Name: auth_access_requests auth_access_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_access_requests
    ADD CONSTRAINT auth_access_requests_pkey PRIMARY KEY (id);


--
-- Name: auth_access_requests auth_access_requests_token_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_access_requests
    ADD CONSTRAINT auth_access_requests_token_key UNIQUE (token);


--
-- Name: auth_tokens auth_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_tokens
    ADD CONSTRAINT auth_tokens_pkey PRIMARY KEY (id);


--
-- Name: auth_tokens auth_tokens_token_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_tokens
    ADD CONSTRAINT auth_tokens_token_hash_key UNIQUE (token_hash);


--
-- Name: case_logs case_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.case_logs
    ADD CONSTRAINT case_logs_pkey PRIMARY KEY (id);


--
-- Name: chunks chunks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chunks
    ADD CONSTRAINT chunks_pkey PRIMARY KEY (id);


--
-- Name: clinician_events clinician_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clinician_events
    ADD CONSTRAINT clinician_events_pkey PRIMARY KEY (id);


--
-- Name: clinics clinics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clinics
    ADD CONSTRAINT clinics_pkey PRIMARY KEY (id);


--
-- Name: complication_alerts complication_alerts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.complication_alerts
    ADD CONSTRAINT complication_alerts_pkey PRIMARY KEY (id);


--
-- Name: complication_cases complication_cases_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.complication_cases
    ADD CONSTRAINT complication_cases_pkey PRIMARY KEY (id);


--
-- Name: complication_monitors complication_monitors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.complication_monitors
    ADD CONSTRAINT complication_monitors_pkey PRIMARY KEY (id);


--
-- Name: conversations conversations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_pkey PRIMARY KEY (id);


--
-- Name: documents_meta documents_meta_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents_meta
    ADD CONSTRAINT documents_meta_pkey PRIMARY KEY (source_id);


--
-- Name: documents documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_pkey PRIMARY KEY (id);


--
-- Name: documents documents_source_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_source_id_key UNIQUE (source_id);


--
-- Name: dosing_rules dosing_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dosing_rules
    ADD CONSTRAINT dosing_rules_pkey PRIMARY KEY (id);


--
-- Name: growth_api_keys growth_api_keys_key_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.growth_api_keys
    ADD CONSTRAINT growth_api_keys_key_hash_key UNIQUE (key_hash);


--
-- Name: growth_api_keys growth_api_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.growth_api_keys
    ADD CONSTRAINT growth_api_keys_pkey PRIMARY KEY (id);


--
-- Name: growth_bookmarks growth_bookmarks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.growth_bookmarks
    ADD CONSTRAINT growth_bookmarks_pkey PRIMARY KEY (id);


--
-- Name: growth_knowledge_chunks growth_knowledge_chunks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.growth_knowledge_chunks
    ADD CONSTRAINT growth_knowledge_chunks_pkey PRIMARY KEY (id);


--
-- Name: growth_paper_alert_items growth_paper_alert_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.growth_paper_alert_items
    ADD CONSTRAINT growth_paper_alert_items_pkey PRIMARY KEY (id);


--
-- Name: growth_paper_subscriptions growth_paper_subscriptions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.growth_paper_subscriptions
    ADD CONSTRAINT growth_paper_subscriptions_pkey PRIMARY KEY (id);


--
-- Name: growth_patient_exports growth_patient_exports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.growth_patient_exports
    ADD CONSTRAINT growth_patient_exports_pkey PRIMARY KEY (id);


--
-- Name: growth_query_logs growth_query_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.growth_query_logs
    ADD CONSTRAINT growth_query_logs_pkey PRIMARY KEY (id);


--
-- Name: growth_session_report_items growth_session_report_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.growth_session_report_items
    ADD CONSTRAINT growth_session_report_items_pkey PRIMARY KEY (id);


--
-- Name: growth_session_reports growth_session_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.growth_session_reports
    ADD CONSTRAINT growth_session_reports_pkey PRIMARY KEY (id);


--
-- Name: ingestion_runs ingestion_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingestion_runs
    ADD CONSTRAINT ingestion_runs_pkey PRIMARY KEY (run_id);


--
-- Name: llm_provider_configs llm_provider_configs_org_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.llm_provider_configs
    ADD CONSTRAINT llm_provider_configs_org_id_key UNIQUE (org_id);


--
-- Name: llm_provider_configs llm_provider_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.llm_provider_configs
    ADD CONSTRAINT llm_provider_configs_pkey PRIMARY KEY (id);


--
-- Name: memberships memberships_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memberships
    ADD CONSTRAINT memberships_pkey PRIMARY KEY (id);


--
-- Name: memberships memberships_user_id_clinic_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memberships
    ADD CONSTRAINT memberships_user_id_clinic_id_key UNIQUE (user_id, clinic_id);


--
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);


--
-- Name: monitor_submissions monitor_submissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monitor_submissions
    ADD CONSTRAINT monitor_submissions_pkey PRIMARY KEY (id);


--
-- Name: network_case_logs network_case_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_case_logs
    ADD CONSTRAINT network_case_logs_pkey PRIMARY KEY (id);


--
-- Name: organizations organizations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_pkey PRIMARY KEY (id);


--
-- Name: organizations organizations_slug_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_slug_key UNIQUE (slug);


--
-- Name: pilot_cases pilot_cases_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pilot_cases
    ADD CONSTRAINT pilot_cases_pkey PRIMARY KEY (case_id);


--
-- Name: pilot_documentation pilot_documentation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pilot_documentation
    ADD CONSTRAINT pilot_documentation_pkey PRIMARY KEY (doc_id);


--
-- Name: pilot_events pilot_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pilot_events
    ADD CONSTRAINT pilot_events_pkey PRIMARY KEY (event_id);


--
-- Name: pilot_sites pilot_sites_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pilot_sites
    ADD CONSTRAINT pilot_sites_pkey PRIMARY KEY (site_id);


--
-- Name: pilot_users pilot_users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pilot_users
    ADD CONSTRAINT pilot_users_pkey PRIMARY KEY (user_id);


--
-- Name: pipeline_checkpoints pipeline_checkpoints_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_checkpoints
    ADD CONSTRAINT pipeline_checkpoints_pkey PRIMARY KEY (checkpoint_id);


--
-- Name: pmc_fulltext pmc_fulltext_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pmc_fulltext
    ADD CONSTRAINT pmc_fulltext_pkey PRIMARY KEY (pmc_id);


--
-- Name: pmid_queue pmid_queue_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pmid_queue
    ADD CONSTRAINT pmid_queue_pkey PRIMARY KEY (id);


--
-- Name: pmid_queue pmid_queue_run_id_pmid_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pmid_queue
    ADD CONSTRAINT pmid_queue_run_id_pmid_key UNIQUE (run_id, pmid);


--
-- Name: practitioner_risk_scores practitioner_risk_scores_clinic_id_practitioner_name_period_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.practitioner_risk_scores
    ADD CONSTRAINT practitioner_risk_scores_clinic_id_practitioner_name_period_key UNIQUE (clinic_id, practitioner_name, period_start, period_end);


--
-- Name: practitioner_risk_scores practitioner_risk_scores_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.practitioner_risk_scores
    ADD CONSTRAINT practitioner_risk_scores_pkey PRIMARY KEY (id);


--
-- Name: publication_syncs publication_syncs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.publication_syncs
    ADD CONSTRAINT publication_syncs_pkey PRIMARY KEY (id);


--
-- Name: publications publications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.publications
    ADD CONSTRAINT publications_pkey PRIMARY KEY (pmid);


--
-- Name: queries queries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.queries
    ADD CONSTRAINT queries_pkey PRIMARY KEY (id);


--
-- Name: query_logs_v2 query_logs_v2_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.query_logs_v2
    ADD CONSTRAINT query_logs_v2_pkey PRIMARY KEY (id);


--
-- Name: safety_reports safety_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.safety_reports
    ADD CONSTRAINT safety_reports_pkey PRIMARY KEY (id);


--
-- Name: saved_protocols saved_protocols_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.saved_protocols
    ADD CONSTRAINT saved_protocols_pkey PRIMARY KEY (id);


--
-- Name: search_history search_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.search_history
    ADD CONSTRAINT search_history_pkey PRIMARY KEY (id);


--
-- Name: user_interests user_interests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_interests
    ADD CONSTRAINT user_interests_pkey PRIMARY KEY (user_id, topic);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: visuals visuals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.visuals
    ADD CONSTRAINT visuals_pkey PRIMARY KEY (id);


--
-- Name: chunks_text_norm_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX chunks_text_norm_trgm ON public.chunks USING gin (text_norm public.gin_trgm_ops);


--
-- Name: chunks_tsv_gin; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX chunks_tsv_gin ON public.chunks USING gin (tsv);


--
-- Name: idx_access_requests_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_access_requests_email ON public.auth_access_requests USING btree (email);


--
-- Name: idx_ae_clinic; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ae_clinic ON public.analytics_events USING btree (clinic_id);


--
-- Name: idx_ae_ts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ae_ts ON public.analytics_events USING btree (created_at DESC);


--
-- Name: idx_ae_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ae_type ON public.analytics_events USING btree (event_type);


--
-- Name: idx_alerts_clinic; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_clinic ON public.complication_alerts USING btree (clinic_id);


--
-- Name: idx_alerts_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_created ON public.complication_alerts USING btree (created_at DESC);


--
-- Name: idx_alerts_dismissed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_dismissed ON public.complication_alerts USING btree (is_dismissed);


--
-- Name: idx_apikeys_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_apikeys_hash ON public.growth_api_keys USING btree (key_hash);


--
-- Name: idx_auth_tokens_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_auth_tokens_hash ON public.auth_tokens USING btree (token_hash);


--
-- Name: idx_auth_tokens_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_auth_tokens_user ON public.auth_tokens USING btree (user_id);


--
-- Name: idx_bookmarks_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bookmarks_user ON public.growth_bookmarks USING btree (user_id);


--
-- Name: idx_caselogs_clinic; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_caselogs_clinic ON public.case_logs USING btree (clinic_id);


--
-- Name: idx_caselogs_comptype; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_caselogs_comptype ON public.case_logs USING btree (complication_type);


--
-- Name: idx_caselogs_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_caselogs_date ON public.case_logs USING btree (event_date DESC);


--
-- Name: idx_caselogs_org; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_caselogs_org ON public.case_logs USING btree (org_id);


--
-- Name: idx_cases_clinic; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cases_clinic ON public.complication_cases USING btree (clinic_id);


--
-- Name: idx_cases_protocol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cases_protocol ON public.complication_cases USING btree (protocol_key);


--
-- Name: idx_cevents_clinic; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cevents_clinic ON public.clinician_events USING btree (clinic_id);


--
-- Name: idx_cevents_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cevents_created ON public.clinician_events USING btree (created_at DESC);


--
-- Name: idx_cevents_section; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cevents_section ON public.clinician_events USING btree (answer_section);


--
-- Name: idx_cevents_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cevents_type ON public.clinician_events USING btree (event_type);


--
-- Name: idx_chunks_chunk_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chunks_chunk_index ON public.chunks USING btree (chunk_index);


--
-- Name: idx_chunks_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chunks_document_id ON public.chunks USING btree (document_id);


--
-- Name: idx_chunks_embedding_hnsw; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chunks_embedding_hnsw ON public.chunks USING ivfflat (embedding public.vector_cosine_ops) WITH (lists='100');


--
-- Name: idx_clinics_org; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_clinics_org ON public.clinics USING btree (org_id);


--
-- Name: idx_docs_meta_evidtype; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_docs_meta_evidtype ON public.documents_meta USING btree (evidence_type);


--
-- Name: idx_docs_meta_pmid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_docs_meta_pmid ON public.documents_meta USING btree (pmid);


--
-- Name: idx_docs_meta_pubtype; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_docs_meta_pubtype ON public.documents_meta USING btree (publication_type);


--
-- Name: idx_docs_meta_source_tier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_docs_meta_source_tier ON public.documents_meta USING btree (source_tier);


--
-- Name: idx_documents_document_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_document_type ON public.documents USING btree (document_type);


--
-- Name: idx_documents_domain; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_domain ON public.documents USING btree (domain);


--
-- Name: idx_documents_fts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_fts ON public.documents USING gin (to_tsvector('english'::regconfig, ((COALESCE(title, ''::text) || ' '::text) || COALESCE(abstract, ''::text))));


--
-- Name: idx_documents_language; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_language ON public.documents USING btree (language);


--
-- Name: idx_documents_specialty; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_specialty ON public.documents USING btree (specialty);


--
-- Name: idx_documents_status_domain_type_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_status_domain_type_year ON public.documents USING btree (status, domain, document_type, year);


--
-- Name: idx_documents_trgm_title; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_trgm_title ON public.documents USING gin (title public.gin_trgm_ops);


--
-- Name: idx_documents_updated_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_updated_at ON public.documents USING btree (updated_at DESC);


--
-- Name: idx_documents_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_year ON public.documents USING btree (year);


--
-- Name: idx_dosing_rules_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_dosing_rules_category ON public.dosing_rules USING btree (category);


--
-- Name: idx_events_clinic; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_events_clinic ON public.analytics_events USING btree (clinic_id);


--
-- Name: idx_events_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_events_created ON public.analytics_events USING btree (created_at DESC);


--
-- Name: idx_events_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_events_type ON public.analytics_events USING btree (event_type);


--
-- Name: idx_ingestion_runs_started; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ingestion_runs_started ON public.ingestion_runs USING btree (started_at DESC);


--
-- Name: idx_ingestion_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ingestion_runs_status ON public.ingestion_runs USING btree (status);


--
-- Name: idx_memberships_clinic; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memberships_clinic ON public.memberships USING btree (clinic_id);


--
-- Name: idx_memberships_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memberships_user ON public.memberships USING btree (user_id);


--
-- Name: idx_monitors_clinic; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_monitors_clinic ON public.complication_monitors USING btree (clinic_id);


--
-- Name: idx_monitors_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_monitors_status ON public.complication_monitors USING btree (monitor_status);


--
-- Name: idx_ncl_clinic; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ncl_clinic ON public.network_case_logs USING btree (clinic_id);


--
-- Name: idx_ncl_comp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ncl_comp ON public.network_case_logs USING btree (complication_type);


--
-- Name: idx_ncl_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ncl_created ON public.network_case_logs USING btree (created_at DESC);


--
-- Name: idx_ncl_org; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ncl_org ON public.network_case_logs USING btree (org_id);


--
-- Name: idx_pilot_cases_site; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pilot_cases_site ON public.pilot_cases USING btree (site_id);


--
-- Name: idx_pilot_docs_case; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pilot_docs_case ON public.pilot_documentation USING btree (case_id);


--
-- Name: idx_pilot_events_case; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pilot_events_case ON public.pilot_events USING btree (case_id);


--
-- Name: idx_pmc_fulltext_pmid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pmc_fulltext_pmid ON public.pmc_fulltext USING btree (pmid);


--
-- Name: idx_pmid_queue_run; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pmid_queue_run ON public.pmid_queue USING btree (run_id);


--
-- Name: idx_pmid_queue_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pmid_queue_status ON public.pmid_queue USING btree (status);


--
-- Name: idx_protocols_archived; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_protocols_archived ON public.saved_protocols USING btree (is_archived);


--
-- Name: idx_protocols_clinic; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_protocols_clinic ON public.saved_protocols USING btree (clinic_id);


--
-- Name: idx_prs_clinic; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_prs_clinic ON public.practitioner_risk_scores USING btree (clinic_id);


--
-- Name: idx_prs_generated; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_prs_generated ON public.practitioner_risk_scores USING btree (generated_at DESC);


--
-- Name: idx_prs_level; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_prs_level ON public.practitioner_risk_scores USING btree (risk_level);


--
-- Name: idx_psubs_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_psubs_user ON public.growth_paper_subscriptions USING btree (user_id);


--
-- Name: idx_publications_doi; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_publications_doi ON public.publications USING btree (doi) WHERE (doi IS NOT NULL);


--
-- Name: idx_publications_journal; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_publications_journal ON public.publications USING btree (journal);


--
-- Name: idx_publications_source_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_publications_source_type ON public.publications USING btree (source_type);


--
-- Name: idx_publications_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_publications_year ON public.publications USING btree (year);


--
-- Name: idx_qlogs_clinic; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_qlogs_clinic ON public.growth_query_logs USING btree (clinic_id);


--
-- Name: idx_qlogs_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_qlogs_created ON public.growth_query_logs USING btree (created_at DESC);


--
-- Name: idx_qlv2_clinic; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_qlv2_clinic ON public.query_logs_v2 USING btree (clinic_id);


--
-- Name: idx_qlv2_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_qlv2_created ON public.query_logs_v2 USING btree (created_at DESC);


--
-- Name: idx_queries_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_queries_created_at ON public.queries USING btree (created_at);


--
-- Name: idx_reports_clinic; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_reports_clinic ON public.safety_reports USING btree (clinic_id);


--
-- Name: idx_sp_clinic; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sp_clinic ON public.saved_protocols USING btree (clinic_id);


--
-- Name: idx_sp_org; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sp_org ON public.saved_protocols USING btree (org_id);


--
-- Name: idx_sr_clinic; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sr_clinic ON public.safety_reports USING btree (clinic_id);


--
-- Name: idx_sreports_clinic; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sreports_clinic ON public.growth_session_reports USING btree (clinic_id);


--
-- Name: idx_sritems_report; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sritems_report ON public.growth_session_report_items USING btree (report_id);


--
-- Name: idx_submissions_alert; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_submissions_alert ON public.monitor_submissions USING btree (alert_triggered);


--
-- Name: idx_submissions_monitor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_submissions_monitor ON public.monitor_submissions USING btree (monitor_id);


--
-- Name: idx_syncs_started_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_syncs_started_at ON public.publication_syncs USING btree (started_at DESC);


--
-- Name: idx_user_interests_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_interests_user ON public.user_interests USING btree (user_id);


--
-- Name: idx_users_clinic; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_clinic ON public.users USING btree (clinic_id);


--
-- Name: idx_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_email ON public.users USING btree (email);


--
-- Name: idx_visuals_conv_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_visuals_conv_created ON public.visuals USING btree (conversation_id, created_at DESC);


--
-- Name: idx_visuals_user_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_visuals_user_created ON public.visuals USING btree (user_id, created_at DESC);


--
-- Name: uq_chunks_doc_chunkindex; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_chunks_doc_chunkindex ON public.chunks USING btree (document_id, chunk_index);


--
-- Name: analytics_events analytics_events_clinic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_events
    ADD CONSTRAINT analytics_events_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES public.clinics(id);


--
-- Name: analytics_events analytics_events_org_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_events
    ADD CONSTRAINT analytics_events_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id);


--
-- Name: analytics_events analytics_events_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_events
    ADD CONSTRAINT analytics_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: answers answers_query_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.answers
    ADD CONSTRAINT answers_query_id_fkey FOREIGN KEY (query_id) REFERENCES public.queries(id) ON DELETE CASCADE;


--
-- Name: case_logs case_logs_clinic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.case_logs
    ADD CONSTRAINT case_logs_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES public.clinics(id) ON DELETE CASCADE;


--
-- Name: case_logs case_logs_org_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.case_logs
    ADD CONSTRAINT case_logs_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: chunks chunks_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chunks
    ADD CONSTRAINT chunks_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: clinics clinics_org_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clinics
    ADD CONSTRAINT clinics_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: growth_paper_alert_items growth_paper_alert_items_subscription_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.growth_paper_alert_items
    ADD CONSTRAINT growth_paper_alert_items_subscription_id_fkey FOREIGN KEY (subscription_id) REFERENCES public.growth_paper_subscriptions(id) ON DELETE CASCADE;


--
-- Name: growth_session_report_items growth_session_report_items_report_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.growth_session_report_items
    ADD CONSTRAINT growth_session_report_items_report_id_fkey FOREIGN KEY (report_id) REFERENCES public.growth_session_reports(id) ON DELETE CASCADE;


--
-- Name: memberships memberships_clinic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memberships
    ADD CONSTRAINT memberships_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES public.clinics(id) ON DELETE CASCADE;


--
-- Name: memberships memberships_org_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memberships
    ADD CONSTRAINT memberships_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: memberships memberships_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memberships
    ADD CONSTRAINT memberships_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: monitor_submissions monitor_submissions_monitor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monitor_submissions
    ADD CONSTRAINT monitor_submissions_monitor_id_fkey FOREIGN KEY (monitor_id) REFERENCES public.complication_monitors(id) ON DELETE CASCADE;


--
-- Name: network_case_logs network_case_logs_clinic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_case_logs
    ADD CONSTRAINT network_case_logs_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES public.clinics(id);


--
-- Name: network_case_logs network_case_logs_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_case_logs
    ADD CONSTRAINT network_case_logs_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: network_case_logs network_case_logs_org_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_case_logs
    ADD CONSTRAINT network_case_logs_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id);


--
-- Name: pilot_cases pilot_cases_site_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pilot_cases
    ADD CONSTRAINT pilot_cases_site_id_fkey FOREIGN KEY (site_id) REFERENCES public.pilot_sites(site_id);


--
-- Name: pilot_documentation pilot_documentation_case_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pilot_documentation
    ADD CONSTRAINT pilot_documentation_case_id_fkey FOREIGN KEY (case_id) REFERENCES public.pilot_cases(case_id);


--
-- Name: pilot_events pilot_events_case_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pilot_events
    ADD CONSTRAINT pilot_events_case_id_fkey FOREIGN KEY (case_id) REFERENCES public.pilot_cases(case_id);


--
-- Name: pilot_users pilot_users_site_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pilot_users
    ADD CONSTRAINT pilot_users_site_id_fkey FOREIGN KEY (site_id) REFERENCES public.pilot_sites(site_id);


--
-- Name: pipeline_checkpoints pipeline_checkpoints_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_checkpoints
    ADD CONSTRAINT pipeline_checkpoints_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.ingestion_runs(run_id);


--
-- Name: pmc_fulltext pmc_fulltext_pmid_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pmc_fulltext
    ADD CONSTRAINT pmc_fulltext_pmid_fkey FOREIGN KEY (pmid) REFERENCES public.publications(pmid);


--
-- Name: pmid_queue pmid_queue_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pmid_queue
    ADD CONSTRAINT pmid_queue_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.ingestion_runs(run_id);


--
-- Name: safety_reports safety_reports_case_log_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.safety_reports
    ADD CONSTRAINT safety_reports_case_log_id_fkey FOREIGN KEY (case_log_id) REFERENCES public.network_case_logs(id);


--
-- Name: safety_reports safety_reports_clinic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.safety_reports
    ADD CONSTRAINT safety_reports_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES public.clinics(id);


--
-- Name: safety_reports safety_reports_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.safety_reports
    ADD CONSTRAINT safety_reports_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: safety_reports safety_reports_org_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.safety_reports
    ADD CONSTRAINT safety_reports_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id);


--
-- Name: saved_protocols saved_protocols_clinic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.saved_protocols
    ADD CONSTRAINT saved_protocols_clinic_id_fkey FOREIGN KEY (clinic_id) REFERENCES public.clinics(id);


--
-- Name: saved_protocols saved_protocols_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.saved_protocols
    ADD CONSTRAINT saved_protocols_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: saved_protocols saved_protocols_org_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.saved_protocols
    ADD CONSTRAINT saved_protocols_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id);


--
-- PostgreSQL database dump complete
--

