# top_jobs.py
#!/usr/bin/env python3
import argparse, json, sys
from scraper.database.db_manager import DatabaseManager

def get_top_jobs(limit: int) -> list[dict]:
    db = DatabaseManager()
    db.connect()
    db.cursor.execute("""
        SELECT title, company, url, ai_score, ai_recommendation, location, salary
        FROM job_offers
        WHERE ai_score IS NOT NULL
            AND applied IS FALSE
            AND is_active IS TRUE
            AND ignored IS FALSE
        ORDER BY ai_score DESC
        LIMIT %s
    """, (limit,))
    rows = db.cursor.fetchall()
    db.close()
    return [
        {"title": r[0], "company": r[1], "url": r[2],
         "score": r[3], "comment": r[4], "location": r[5], "salary": r[6]}
        for r in rows
    ]

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    results = get_top_jobs(args.limit)
    print(json.dumps(results, ensure_ascii=False))