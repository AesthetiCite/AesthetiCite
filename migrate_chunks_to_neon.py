#!/usr/bin/env python3
"""
Stream chunks table from source DB to Neon using COPY for speed.
Uses psql COPY TO STDOUT piped to COPY FROM STDIN.
Excludes generated columns (tsv, text_norm).
"""
import os, sys, time, subprocess
from datetime import datetime

SOURCE_URL = os.getenv("DATABASE_URL")
NEON_URL = "postgresql://neondb_owner:npg_puKL9Pd7UMfG@ep-odd-star-amqythz1.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require"
LOG_FILE = "/home/runner/workspace/chunks_migrate.log"

COLS = "id, document_id, chunk_index, text, page_or_section, evidence_level, embedding, created_at"

def log(msg):
    line = f"[{datetime.utcnow().isoformat()}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def main():
    log(f"Starting chunks COPY migration")
    log(f"Source: {SOURCE_URL[:50]}...")
    log(f"Target: neon.tech")
    
    # Use psql COPY command piped directly
    # This is the fastest approach - bypasses Python overhead entirely
    copy_out_sql = f"COPY (SELECT {COLS} FROM chunks) TO STDOUT WITH (FORMAT binary)"
    copy_in_sql = f"COPY chunks ({COLS}) FROM STDIN WITH (FORMAT binary)"
    
    log(f"Starting COPY pipeline (binary format for speed)...")
    t0 = time.time()
    
    # Use a pipe: psql source -> psql neon
    psql_out = subprocess.Popen(
        ["psql", SOURCE_URL, "-c", copy_out_sql],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    psql_in = subprocess.Popen(
        ["psql", NEON_URL, "-c", copy_in_sql],
        stdin=psql_out.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Close source output fd in the parent (allow SIGPIPE to work)
    psql_out.stdout.close()
    
    # Monitor progress every 30 seconds
    log("COPY pipeline started. Monitoring...")
    while True:
        try:
            psql_in.wait(timeout=30)
            break
        except subprocess.TimeoutExpired:
            elapsed = time.time() - t0
            log(f"  Still running... {elapsed/60:.1f} min elapsed")
    
    elapsed = time.time() - t0
    
    # Get results
    stdout, stderr = psql_in.communicate()
    out_stdout, out_stderr = psql_out.communicate()
    
    rc_in = psql_in.returncode
    rc_out = psql_out.returncode
    
    log(f"COPY finished in {elapsed/60:.1f} min")
    log(f"Source psql exit code: {rc_out}")
    log(f"Target psql exit code: {rc_in}")
    
    if out_stderr:
        log(f"Source stderr: {out_stderr.decode()[:500]}")
    if stderr:
        log(f"Target stderr: {stderr.decode()[:500]}")
    if stdout:
        log(f"Target stdout: {stdout.decode()[:200]}")
    
    if rc_in == 0 and rc_out == 0:
        log("SUCCESS! Chunks data copied to Neon.")
    else:
        log(f"FAILED with exit codes: source={rc_out}, target={rc_in}")
        sys.exit(1)

if __name__ == "__main__":
    main()
