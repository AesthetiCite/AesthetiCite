"""
AesthetiCite Publication Sync Scheduler

Configures automated daily publication sync starting January 30, 2026.
Runs at 02:00 UTC daily to download maximum publications across all
25 supported languages and all medical fields.

Usage:
    python -m app.agents.sync_schedule

This script can be run as a cron job or scheduled task:
    0 2 * * * cd /path/to/aestheticite && python -m app.agents.sync_schedule
"""

import os
import sys
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.agents.multilang_sync import run_multilingual_sync, LANGUAGE_CODES, MULTILINGUAL_QUERIES

SYNC_START_DATE = date(2026, 1, 30)
SYNC_SCHEDULE_HOUR = 2
MAX_PAPERS_PER_QUERY = 500
DELAY_BETWEEN_QUERIES = 0.35

def get_sync_summary():
    """Get summary of sync configuration."""
    total_queries = sum(len(queries) for queries in MULTILINGUAL_QUERIES.values())
    return {
        "languages": len(LANGUAGE_CODES),
        "total_queries": total_queries,
        "max_per_query": MAX_PAPERS_PER_QUERY,
        "estimated_max_papers": total_queries * MAX_PAPERS_PER_QUERY,
        "start_date": SYNC_START_DATE.isoformat(),
        "schedule": f"Daily at {SYNC_SCHEDULE_HOUR:02d}:00 UTC",
    }


def should_run_sync() -> bool:
    """Check if sync should run today."""
    today = date.today()
    if today < SYNC_START_DATE:
        print(f"Sync not started yet. Start date: {SYNC_START_DATE}")
        return False
    return True


def run_scheduled_sync():
    """Run the scheduled publication sync."""
    print("\n" + "=" * 60)
    print("AesthetiCite Scheduled Publication Sync")
    print("=" * 60)
    
    summary = get_sync_summary()
    print(f"Start Date: {summary['start_date']}")
    print(f"Schedule: {summary['schedule']}")
    print(f"Languages: {summary['languages']}")
    print(f"Total Queries: {summary['total_queries']}")
    print(f"Max Papers per Query: {summary['max_per_query']}")
    print(f"Estimated Maximum Papers: {summary['estimated_max_papers']:,}")
    print("=" * 60 + "\n")
    
    if not should_run_sync():
        print("Sync skipped - not yet at start date.")
        return None
    
    print(f"Starting sync at {datetime.utcnow().isoformat()} UTC")
    
    stats = run_multilingual_sync(
        max_per_query=MAX_PAPERS_PER_QUERY,
        delay_between_queries=DELAY_BETWEEN_QUERIES
    )
    
    print(f"\nSync completed at {datetime.utcnow().isoformat()} UTC")
    return stats


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="AesthetiCite Scheduled Publication Sync",
        epilog="Runs daily at 02:00 UTC starting January 30, 2026"
    )
    parser.add_argument("--info", action="store_true", help="Show sync configuration info only")
    parser.add_argument("--force", action="store_true", help="Run sync even before start date")
    args = parser.parse_args()
    
    if args.info:
        summary = get_sync_summary()
        print("\nAesthetiCite Publication Sync Configuration")
        print("-" * 40)
        for key, value in summary.items():
            print(f"  {key}: {value}")
        print()
    elif args.force:
        print("Force running sync (ignoring start date)...")
        run_multilingual_sync(
            max_per_query=MAX_PAPERS_PER_QUERY,
            delay_between_queries=DELAY_BETWEEN_QUERIES
        )
    else:
        run_scheduled_sync()
