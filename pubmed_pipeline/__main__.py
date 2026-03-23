"""
PubMed Pipeline CLI
===================

Commands:
    python -m pubmed_pipeline init                     Initialize database schema
    python -m pubmed_pipeline plan --config corpus.yaml
    python -m pubmed_pipeline fetch --run-id <id> --batch-size 500
    python -m pubmed_pipeline incremental --days 7
    python -m pubmed_pipeline export --format jsonl --out data/pubmed.jsonl
    python -m pubmed_pipeline stats
"""

import argparse
import logging
import json
import sys
from pathlib import Path

from pubmed_pipeline.utils.config import CorpusConfig, get_db_url
from pubmed_pipeline.models.schema import init_schema, SCHEMA_SQL
from pubmed_pipeline.stages.planner import QueryPlanner
from pubmed_pipeline.stages.fetcher import PubMedFetcher
from pubmed_pipeline.stages.storage import PublicationStorage, IngestionRunManager
from pubmed_pipeline.stages.exporter import PublicationExporter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

def cmd_init(args):
    """Initialize database schema."""
    from sqlalchemy import create_engine
    db_url = get_db_url()
    if not db_url:
        logger.error("DATABASE_URL not set")
        return 1
    engine = create_engine(db_url)
    init_schema(engine)
    logger.info("Database schema initialized")
    return 0

def cmd_plan(args):
    """Run query planning stage."""
    config = CorpusConfig.from_yaml(args.config)
    logger.info(f"Loaded config: {config.name} v{config.version}")
    logger.info(f"Target: {config.target_total} publications, {len(config.query_groups)} query groups")
    
    planner = QueryPlanner(config)
    result = planner.run()
    
    print("\n" + "=" * 60)
    print("QUERY PLAN COMPLETE")
    print("=" * 60)
    print(f"Total unique PMIDs: {result.total_pmids}")
    print("\nBy Tier:")
    for tier, count in result.pmids_by_tier.items():
        print(f"  {tier}: {count}")
    print("\nBy Group:")
    for group, count in result.pmids_by_group.items():
        print(f"  {group}: {count}")
    
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, 'w') as f:
            json.dump({
                "pmids": list(result.all_pmids),
                "coverage": result.coverage_report,
            }, f)
        logger.info(f"Saved {result.total_pmids} PMIDs to {args.output}")
    
    return 0

def cmd_fetch(args):
    """Fetch publications from PubMed."""
    db_url = get_db_url()
    if not db_url:
        logger.error("DATABASE_URL not set")
        return 1
    
    if args.pmids_file:
        with open(args.pmids_file) as f:
            data = json.load(f)
            pmids = data.get("pmids", data) if isinstance(data, dict) else data
    else:
        logger.error("Provide --pmids-file with list of PMIDs to fetch")
        return 1
    
    run_manager = IngestionRunManager(db_url)
    run_id = run_manager.create_run("backfill", "manual", {"source": args.pmids_file})
    logger.info(f"Created run ID: {run_id}")
    
    storage = PublicationStorage(db_url)
    existing = storage.get_existing_pmids()
    new_pmids = [p for p in pmids if p not in existing]
    logger.info(f"Found {len(pmids)} PMIDs, {len(new_pmids)} new to fetch")
    
    if args.limit:
        new_pmids = new_pmids[:args.limit]
    
    fetcher = PubMedFetcher(
        rate_limit_qps=args.qps,
        save_raw=args.save_raw,
        raw_dir=args.raw_dir
    )
    
    try:
        publications = fetcher.fetch_all(new_pmids, batch_size=args.batch_size)
        logger.info(f"Fetched {len(publications)} publications")
        
        result = storage.store_batch(publications, run_id)
        logger.info(f"Stored: {result['stored']}, Skipped: {result['skipped']}, Failed: {result['failed']}")
        
        run_manager.complete_run(run_id, {
            "found": len(pmids),
            "fetched": len(publications),
            "stored": result["stored"],
            "skipped": result["skipped"],
            "failed": result["failed"],
        })
        
    except Exception as e:
        logger.error(f"Fetch failed: {e}")
        run_manager.fail_run(run_id, str(e))
        return 1
    
    return 0

def cmd_incremental(args):
    """Run incremental update for recent publications."""
    from pubmed_pipeline.stages.planner import QueryPlanner
    
    db_url = get_db_url()
    if not db_url:
        logger.error("DATABASE_URL not set")
        return 1
    
    config_path = args.config or "corpus.yaml"
    if not Path(config_path).exists():
        logger.error(f"Config not found: {config_path}")
        return 1
    
    config = CorpusConfig.from_yaml(config_path)
    
    from datetime import datetime, timedelta
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days)
    date_range = (start_date.strftime("%Y/%m/%d"), end_date.strftime("%Y/%m/%d"))
    
    for group in config.query_groups:
        group.date_range = date_range
    
    run_manager = IngestionRunManager(db_url)
    run_id = run_manager.create_run("incremental", config.hash(), {"days": args.days})
    
    planner = QueryPlanner(config)
    plan_result = planner.run()
    logger.info(f"Found {plan_result.total_pmids} PMIDs in last {args.days} days")
    
    storage = PublicationStorage(db_url)
    existing = storage.get_existing_pmids()
    new_pmids = [p for p in plan_result.all_pmids if p not in existing]
    logger.info(f"New PMIDs to fetch: {len(new_pmids)}")
    
    if not new_pmids:
        logger.info("No new publications to fetch")
        run_manager.complete_run(run_id, {"found": 0, "fetched": 0, "stored": 0, "skipped": 0, "failed": 0})
        return 0
    
    fetcher = PubMedFetcher(rate_limit_qps=args.qps)
    
    try:
        publications = fetcher.fetch_all(new_pmids, batch_size=args.batch_size)
        result = storage.store_batch(publications, run_id)
        
        run_manager.complete_run(run_id, {
            "found": len(new_pmids),
            "fetched": len(publications),
            "stored": result["stored"],
            "skipped": result["skipped"],
            "failed": result["failed"],
        })
        
        logger.info(f"Incremental update complete: {result['stored']} new publications")
        
    except Exception as e:
        logger.error(f"Incremental update failed: {e}")
        run_manager.fail_run(run_id, str(e))
        return 1
    
    return 0

def cmd_export(args):
    """Export publications to JSONL."""
    db_url = get_db_url()
    if not db_url:
        logger.error("DATABASE_URL not set")
        return 1
    
    exporter = PublicationExporter(db_url)
    
    if args.format == "aestheticite":
        count = exporter.export_for_aestheticite(args.output, limit=args.limit)
    else:
        count = exporter.export_jsonl(
            args.output,
            source_types=args.types.split(",") if args.types else None,
            min_year=args.min_year,
            limit=args.limit,
            compress=args.compress
        )
    
    print(f"Exported {count} publications to {args.output}")
    return 0

def cmd_stats(args):
    """Show publication statistics."""
    db_url = get_db_url()
    if not db_url:
        logger.error("DATABASE_URL not set")
        return 1
    
    exporter = PublicationExporter(db_url)
    stats = exporter.get_stats()
    
    print("\n" + "=" * 60)
    print("PUBLICATION STATISTICS")
    print("=" * 60)
    print(f"\nTotal Publications: {stats['total_publications']:,}")
    
    print("\nBy Source Type:")
    for item in stats['by_source_type']:
        print(f"  {item['type']:15} {item['count']:>10,}  (avg rank: {item['avg_rank']:.1f})")
    
    print("\nBy Year (recent):")
    for item in stats['by_year'][:10]:
        print(f"  {item['year']}: {item['count']:,}")
    
    print("\nTop Journals:")
    for item in stats['top_journals'][:10]:
        print(f"  {item['journal'][:40]:40} {item['count']:>8,}")
    
    print("\nTop MeSH Terms:")
    for item in stats['top_mesh_terms'][:15]:
        print(f"  {item['term'][:40]:40} {item['count']:>8,}")
    
    return 0

def main():
    parser = argparse.ArgumentParser(
        prog="pubmed_pipeline",
        description="PubMed Harvesting Pipeline for AesthetiCite"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    init_p = subparsers.add_parser("init", help="Initialize database schema")
    
    plan_p = subparsers.add_parser("plan", help="Run query planning")
    plan_p.add_argument("--config", required=True, help="Path to corpus.yaml")
    plan_p.add_argument("--output", "-o", help="Output file for PMIDs")
    
    fetch_p = subparsers.add_parser("fetch", help="Fetch publications")
    fetch_p.add_argument("--pmids-file", required=True, help="JSON file with PMIDs")
    fetch_p.add_argument("--batch-size", type=int, default=200, help="Batch size for fetching")
    fetch_p.add_argument("--qps", type=float, default=3.0, help="Queries per second")
    fetch_p.add_argument("--limit", type=int, help="Limit number of PMIDs")
    fetch_p.add_argument("--save-raw", action="store_true", help="Save raw XML responses")
    fetch_p.add_argument("--raw-dir", default="data/raw", help="Directory for raw responses")
    
    inc_p = subparsers.add_parser("incremental", help="Incremental update")
    inc_p.add_argument("--days", type=int, default=7, help="Days back to search")
    inc_p.add_argument("--config", help="Path to corpus.yaml")
    inc_p.add_argument("--batch-size", type=int, default=200, help="Batch size")
    inc_p.add_argument("--qps", type=float, default=3.0, help="Queries per second")
    
    exp_p = subparsers.add_parser("export", help="Export publications")
    exp_p.add_argument("--format", choices=["jsonl", "aestheticite"], default="jsonl")
    exp_p.add_argument("--output", "-o", required=True, help="Output file path")
    exp_p.add_argument("--types", help="Comma-separated source types to include")
    exp_p.add_argument("--min-year", type=int, help="Minimum publication year")
    exp_p.add_argument("--limit", type=int, help="Limit number of records")
    exp_p.add_argument("--compress", action="store_true", help="Gzip output")
    
    stats_p = subparsers.add_parser("stats", help="Show statistics")
    
    args = parser.parse_args()
    
    if args.command == "init":
        return cmd_init(args)
    elif args.command == "plan":
        return cmd_plan(args)
    elif args.command == "fetch":
        return cmd_fetch(args)
    elif args.command == "incremental":
        return cmd_incremental(args)
    elif args.command == "export":
        return cmd_export(args)
    elif args.command == "stats":
        return cmd_stats(args)
    else:
        parser.print_help()
        return 0

if __name__ == "__main__":
    sys.exit(main())
