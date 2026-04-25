#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CLI pour scorer les offres d'emploi en attente avec l'IA.

Utilise le module scoring.ai_scorer pour évaluer les offres
qui n'ont pas encore été scorées.
"""

import argparse
import logging
import sys
from pathlib import Path

# Ajouter le répertoire racine au path
sys.path.insert(0, str(Path(__file__).parent))

from scraper.database.db_manager import DatabaseManager
from scoring.ai_scorer import score_pending_jobs

def setup_logging():
    """Configure le logging pour l'application."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()
        ]
    )

def main():
    """Fonction principale."""
    parser = argparse.ArgumentParser(
        description="Score les offres d'emploi en attente avec l'IA"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Nombre maximum d'offres à scorer (défaut: 20)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Scorer toutes les offres en attente (ignore --limit)"
    )
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("=" * 70)
    logger.info("SCRAPING AI - SCORING DES OFFRES")
    logger.info("=" * 70)

    # Vérifier la clé API
    api_key = Path('.env').exists()
    if not api_key:
        logger.warning("Fichier .env non trouvé. Assurez-vous que OPENROUTER_API_KEY est définie.")

    # Connexion à la base de données
    try:
        with DatabaseManager() as db:
            db.connect()
            db.create_table()

            # Déterminer la limite
            limit = None if args.all else args.limit
            if args.all:
                logger.info("Mode : toutes les offres en attente")
            else:
                logger.info(f"Mode : limité à {args.limit} offres")

            scored_count = score_pending_jobs(db, limit=limit)

            logger.info("=" * 70)
            logger.info(f"RÉSUMÉ : {scored_count} offres scorées")
            logger.info("=" * 70)

    except Exception as e:
        logger.error(f"Erreur lors du scoring : {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
