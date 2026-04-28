#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Manage job offers database: view, filter, and apply to offers.
"""

import argparse
import logging
from datetime import datetime
from pathlib import Path
from tabulate import tabulate
import pandas as pd
from scraper.database.db_manager import DatabaseManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _has_scoring_columns(db: DatabaseManager) -> bool:
    """Check if ai_score and ai_recommendation columns exist."""
    try:
        query = """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='job_offers' AND column_name='ai_score'
            );
        """
        db.cursor.execute(query)
        return db.cursor.fetchone()[0]
    except Exception as e:
        logger.warning(f"Could not check for scoring columns: {e}")
        return False


def list_offers(db: DatabaseManager, filter_type: str):
    """List job offers with optional filtering."""
    try:
        has_scoring = _has_scoring_columns(db)

        if filter_type == "new":
            base_query = "SELECT url, title, company, new_offer, applied"
            if has_scoring:
                base_query += ", ai_score, ai_recommendation"
            base_query += " FROM job_offers WHERE new_offer = True"
            if has_scoring:
                base_query += " ORDER BY ai_score DESC NULLS LAST, scraped_at DESC"
            else:
                base_query += " ORDER BY scraped_at DESC"
            title = "NEW OFFERS (new_offer = True)"
        elif filter_type == "applied":
            base_query = "SELECT url, title, company, new_offer, applied"
            if has_scoring:
                base_query += ", ai_score, ai_recommendation"
            base_query += " FROM job_offers WHERE applied = True"
            if has_scoring:
                base_query += " ORDER BY ai_score DESC NULLS LAST, scraped_at DESC"
            else:
                base_query += " ORDER BY scraped_at DESC"
            title = "APPLIED OFFERS (applied = True)"
        else:
            base_query = "SELECT url, title, company, new_offer, applied"
            if has_scoring:
                base_query += ", ai_score, ai_recommendation"
            base_query += " FROM job_offers"
            if has_scoring:
                base_query += " ORDER BY ai_score DESC NULLS LAST, scraped_at DESC"
            else:
                base_query += " ORDER BY scraped_at DESC"
            title = "ALL OFFERS"

        db.cursor.execute(base_query)
        rows = db.cursor.fetchall()

        if not rows:
            print(f"\n{title}")
            print("No offers found.")
            return

        # Format for display
        if has_scoring:
            headers = ["URL", "Title", "Company", "New", "Applied", "Score", "Reco"]
            formatted_rows = [
                (
                    row[0][:60] + "..." if len(row[0]) > 60 else row[0],
                    row[1][:40] + "..." if len(row[1]) > 40 else row[1],
                    row[2] or "N/A",
                    "✓" if row[3] else " ",
                    "✓" if row[4] else " ",
                    f"{row[5]:.1f}" if row[5] is not None else "--",
                    row[6] if row[6] else "--"
                )
                for row in rows
            ]
        else:
            headers = ["URL", "Title", "Company", "New", "Applied"]
            formatted_rows = [
                (row[0][:60] + "..." if len(row[0]) > 60 else row[0],
                 row[1][:40] + "..." if len(row[1]) > 40 else row[1],
                 row[2] or "N/A",
                 "✓" if row[3] else " ",
                 "✓" if row[4] else " ")
                for row in rows
            ]

        print(f"\n{title}")
        print(tabulate(formatted_rows, headers=headers, tablefmt="grid"))
        print(f"\nTotal: {len(rows)} offers\n")

    except Exception as e:
        logger.error(f"Error listing offers: {e}")


def apply_offer(db: DatabaseManager, url: str):
    """Mark an offer as applied."""
    try:
        success = db.mark_applied(url)
        if success:
            print(f"\n✓ Offer marked as applied: {url}\n")
        else:
            print(f"\n✗ Offer not found: {url}\n")
    except Exception as e:
        logger.error(f"Error applying offer: {e}")


def handle_export(args, db: DatabaseManager):
    """Export job offers to CSV with optional filters."""
    try:
        # Build query - always select active offers
        query = "SELECT * FROM job_offers WHERE is_active = TRUE"
        params = []

        # Apply --new-only filter if provided
        if args.new_only:
            query += " AND new_offer = TRUE"

        # Apply --min-score filter if provided (check if ai_score column exists)
        if args.min_score is not None:
            # Check if ai_score column exists
            has_scoring = _has_scoring_columns(db)
            if has_scoring:
                query += " AND ai_score >= ?"
                params.append(args.min_score)
            else:
                logger.warning("--min-score requested but ai_score column not found. Ignoring filter.")

        query += " ORDER BY scraped_at DESC"

        # Execute query
        db.cursor.execute(query, params)
        rows = db.cursor.fetchall()

        if not rows:
            logger.info("No job offers match the export criteria.")
            return

        # Get column names
        col_names = [description[0] for description in db.cursor.description]

        # Create DataFrame
        df = pd.DataFrame(rows, columns=col_names)

        # Determine output path
        if args.output:
            output_path = Path(args.output)
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = Path(f"data/export_{timestamp}.csv")

        # Create data/ directory if it doesn't exist
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write CSV
        df.to_csv(output_path, index=False)

        logger.info(f"{len(df)} offres exportées dans {output_path}")

    except Exception as e:
        logger.error(f"Error exporting offers: {e}")


def show_stats(db: DatabaseManager):
    """Show database statistics."""
    try:
        # Total offers
        db.cursor.execute("SELECT COUNT(*) FROM job_offers;")
        total = db.cursor.fetchone()[0]

        # New offers
        db.cursor.execute("SELECT COUNT(*) FROM job_offers WHERE new_offer = True;")
        new_count = db.cursor.fetchone()[0]

        # Applied offers
        db.cursor.execute("SELECT COUNT(*) FROM job_offers WHERE applied = True;")
        applied = db.cursor.fetchone()[0]

        # Inactive (old offers not applied)
        db.cursor.execute("SELECT COUNT(*) FROM job_offers WHERE new_offer = False AND applied = False;")
        inactive = db.cursor.fetchone()[0]

        # Display basic stats
        stats_data = [
            ["Total offers", total],
            ["New offers (to apply)", new_count],
            ["Applied offers", applied],
            ["Inactive offers (old, not applied)", inactive],
        ]

        print("\n" + "=" * 60)
        print("JOB OFFERS STATISTICS")
        print("=" * 60)
        print(tabulate(stats_data, headers=["Metric", "Count"], tablefmt="grid"))

        # Check if scoring columns exist
        try:
            query = """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='job_offers' AND column_name='ai_score'
                );
            """
            db.cursor.execute(query)
            has_scoring = db.cursor.fetchone()[0]
        except Exception as e:
            logger.warning(f"Could not check for scoring columns: {e}")
            has_scoring = False

        # Add scoring stats if available
        if has_scoring:
            # Scored offers
            db.cursor.execute("SELECT COUNT(*) FROM job_offers WHERE ai_score IS NOT NULL;")
            scored_count = db.cursor.fetchone()[0]

            # Average score
            db.cursor.execute("SELECT AVG(ai_score) FROM job_offers WHERE ai_score IS NOT NULL;")
            avg_score_row = db.cursor.fetchone()
            avg_score = avg_score_row[0] if avg_score_row[0] is not None else 0

            # Recommendations distribution - fetch all and normalize by emoji
            db.cursor.execute("""
                SELECT ai_recommendation
                FROM job_offers
                WHERE ai_recommendation IS NOT NULL;
            """)
            reco_rows = db.cursor.fetchall()

            # Normalize: extract emoji or mark as "Non déterminée"
            emoji_counts = {
                '🟢': 0,
                '🟡': 0,
                '🟠': 0,
                '🔴': 0,
                'Non déterminée': 0
            }

            for (reco,) in reco_rows:
                # Extract first emoji if present
                normalized = None
                for emoji in ['🟢', '🟡', '🟠', '🔴']:
                    if emoji in reco:
                        normalized = emoji
                        break
                if not normalized:
                    normalized = "Non déterminée"

                emoji_counts[normalized] += 1

            # Build distribution string in fixed order
            reco_dist = [
                f"🟢 {emoji_counts['🟢']}",
                f"🟡 {emoji_counts['🟡']}",
                f"🟠 {emoji_counts['🟠']}",
                f"🔴 {emoji_counts['🔴']}",
                f"Non déterminée {emoji_counts['Non déterminée']}",
            ]

            # Not scored
            not_scored = total - scored_count if total else 0

            # Add scoring section
            print("-" * 60)
            print("AI SCORING")
            print("-" * 60)

            scoring_data = [
                ["Scored offers", scored_count],
                ["Average score", f"{avg_score:.1f}/10" if avg_score else "N/A"],
                ["Recommandation distribution", " | ".join(reco_dist) if reco_dist else "N/A"],
                ["Not scored yet", not_scored],
            ]
            print(tabulate(scoring_data, headers=["Metric", "Count/Value"], tablefmt="grid"))

        print("=" * 60 + "\n")

    except Exception as e:
        logger.error(f"Error showing stats: {e}")


def ignore_offer(db: DatabaseManager, identifier: str, is_id: bool):
    """Mark an offer as ignored."""
    try:
        success, title = db.mark_ignored(identifier, is_id)
        if success:
            print(f"\n✓ Offer marked as ignored: {title}\n")
        else:
            print(f"\n✗ Offer not found: {identifier}\n")
    except Exception as e:
        logger.error(f"Error ignoring offer: {e}")

def main():
    parser = argparse.ArgumentParser(description="Manage job offers database")

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # list command
    list_parser = subparsers.add_parser("list", help="List job offers")
    list_parser.add_argument(
        "--new",
        action="store_true",
        help="Show only new offers (new_offer=True)"
    )
    list_parser.add_argument(
        "--applied",
        action="store_true",
        help="Show only applied offers (applied=True)"
    )

    # apply command
    apply_parser = subparsers.add_parser("apply", help="Mark an offer as applied")
    apply_parser.add_argument("url", help="URL of the offer to mark as applied")

    # ignore command
    ignore_parser = subparsers.add_parser("ignore", help="Mark an offer as ignored")
    ignore_group = ignore_parser.add_mutually_exclusive_group(required=True)
    ignore_group.add_argument("--id", type=int, help="ID of the offer to ignore")
    ignore_group.add_argument("--url", type=str, help="URL of the offer to ignore")

    # stats command
    subparsers.add_parser("stats", help="Show database statistics")

    # export command
    export_parser = subparsers.add_parser("export", help="Export job offers to CSV")
    export_parser.add_argument(
        "--output",
        type=str,
        help="Path to output CSV file (default: data/export_YYYYMMDD_HHMMSS.csv)"
    )
    export_parser.add_argument(
        "--min-score",
        type=float,
        help="Filter offers with ai_score >= value (optional)"
    )
    export_parser.add_argument(
        "--new-only",
        action="store_true",
        help="Export only new offers (new_offer=True)"
    )

    args = parser.parse_args()

    # Initialize database
    db = DatabaseManager()
    db.connect()
    db.create_table()

    try:
        if args.command == "list":
            if args.new:
                list_offers(db, "new")
            elif args.applied:
                list_offers(db, "applied")
            else:
                list_offers(db, "all")

        elif args.command == "apply":
            apply_offer(db, args.url)

        elif args.command == "ignore":
            identifier = args.id if args.id is not None else args.url
            is_id = args.id is not None
            ignore_offer(db, identifier, is_id)

        elif args.command == "stats":
            show_stats(db)

        elif args.command == "export":
            handle_export(args, db)

        else:
            parser.print_help()

    finally:
        db.close()


if __name__ == "__main__":
    main()
