#!/usr/bin/env python3
"""
Remet à NULL le score des offres avec recommandation non déterminée
pour qu'elles soient re-scorées au prochain run de score_jobs.py
"""
import logging
import sys
from pathlib import Path

# Ajouter le répertoire racine au path
sys.path.insert(0, str(Path(__file__).parent))
from scraper.database.db_manager import DatabaseManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def reset_undetermined(dry_run=False):
    with DatabaseManager() as db:
        # Compte les offres concernées
        db.cursor.execute("""
            SELECT COUNT(*) FROM job_offers 
            WHERE ai_recommendation = 'Non déterminée'
               OR ai_recommendation = 'Indéterminé'
               OR (ai_score IS NOT NULL AND ai_recommendation IS NULL)
        """)
        count = db.cursor.fetchone()[0]
        logger.info(f"Offres avec recommandation non déterminée : {count}")

        if count == 0:
            logger.info("✅ Rien à rescorer.")
            return 0

        if dry_run:
            logger.info("🔍 Dry-run activé, aucune modification.")
            return count

        # Remet le score à NULL pour forcer le re-scoring
        db.cursor.execute("""
            UPDATE job_offers 
            SET ai_score = NULL,
                ai_recommendation = NULL,
                ai_comment = NULL
            WHERE ai_recommendation = 'Non déterminée'
               OR ai_recommendation = 'Indéterminé'
               OR (ai_score IS NOT NULL AND ai_recommendation IS NULL)
        """)
        db.conn.commit()
        logger.info(f"✅ {count} offres remises à NULL, prêtes à être re-scorées.")
        return count

if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    count = reset_undetermined(dry_run=dry_run)
    sys.exit(0 if count >= 0 else 1)