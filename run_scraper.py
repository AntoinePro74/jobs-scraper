#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script principal pour lancer le scraping HelloWork avec export CSV + JSON.
Gère plusieurs URLs de recherche simultanément.
"""

import logging
import json
import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime
from scraper.hellowork_scraper import HelloWorkScraper
from scraper.wttj_scraper import WttjScraper
from scraper.apec_scraper import ApecScraper
from scraper.france_travail_scraper import FranceTravailScraper
from scraper.models.job_offer import JobOffer
from scraper.database.db_manager import DatabaseManager
from config import SEARCH_PROFILES

# Dossier de sortie
OUTPUT_DIR = Path("data")
OUTPUT_DIR.mkdir(exist_ok=True)


def setup_logging():
    """Configure le logging pour l'application."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()
        ]
    )


def save_to_csv(job_offers: list, filename: str):
    """
    Sauvegarde les offres dans un fichier CSV.

    Args:
        job_offers (list): Liste des offres à sauvegarder
        filename (str): Nom du fichier de sortie
    """
    data = [offer.to_dict() for offer in job_offers]
    df = pd.DataFrame(data)
    df.to_csv(filename, index=False, encoding='utf-8-sig')
    logging.info(f"{len(job_offers)} offres sauvegardées dans {filename}")


def save_to_json(job_offers: list, filename: str):
    """
    Sauvegarde les offres dans un fichier JSON.

    Args:
        job_offers (list): Liste des offres à sauvegarder
        filename (str): Nom du fichier de sortie
    """
    data = [offer.to_dict() for offer in job_offers]
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logging.info(f"{len(job_offers)} offres sauvegardées dans {filename}")


def save_to_postgres(job_offers: list):
    """
    Sauvegarde les offres dans PostgreSQL.

    Args:
        job_offers (list): Liste des offres à sauvegarder
    """
    try:
        with DatabaseManager() as db:
            db.create_table()
            inserted = db.insert_job_offers(job_offers)
            logging.info(f"{inserted} offres sauvegardées dans PostgreSQL")
    except Exception as e:
        logging.error(f"Erreur lors de la sauvegarde en PostgreSQL : {e}")
        # Continue execution even if database save fails
        raise


def print_summary(job_offers: list):
    """Affiche un résumé des offres scrapées."""
    print("\n" + "=" * 70)
    print("RÉSUMÉ DES OFFRES COLLECTÉES")
    print("=" * 70)

    for i, offer in enumerate(job_offers, 1):
        print(f"\n[{i}/{len(job_offers)}] {offer.title}")
        print(f"      Entreprise : {offer.company or 'N/A'}")
        print(f"      Localisation : {offer.location or 'N/A'}")
        print(f"      Contrat : {offer.employment_type.value}")
        print(f"      Télétravail : {offer.remote_work.value}")
        print(f"      Salaire : {offer.salary or 'N/A'}")
        print(f"      URL : {offer.url}")

    print("\n" + "=" * 70)


def main():
    """Fonction principale du scraper."""
    # Parser les arguments en ligne de commande
    parser = argparse.ArgumentParser(description="Scraper HelloWork avec pagination et URLs multiples")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Nombre maximum de pages à scraper par URL (par défaut: toutes)"
    )
    parser.add_argument(
        "--urls",
        type=str,
        nargs="+",
        default=None,
        help="URLs de recherche HelloWork (par défaut: URLs prédéfinies)"
    )
    parser.add_argument(
        "--rescrape-existing",
        action="store_true",
        help="Force le re-scraping et la mise à jour en base des offres déjà connues"
    )
    parser.add_argument(
        "--visible",
        action="store_true",
        help="Affiche les navigateurs (mode non-headless)"
    )
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger(__name__)

    # Registre des scrapers disponibles
    SCRAPER_REGISTRY = {
        "hellowork": HelloWorkScraper,
        "wttj": WttjScraper,
        "apec": ApecScraper,
        "france_travail": FranceTravailScraper,
    }

    # Déterminer les URLs à scraper
    if args.urls:
        urls_to_scrape = args.urls
        profiles_to_scrape = [{"label": url, "url": url, "site": "hellowork"} for url in urls_to_scrape]
    else:
        profiles_to_scrape = SEARCH_PROFILES
        urls_to_scrape = [p["url"] for p in profiles_to_scrape]

    logger.info("=" * 70)
    logger.info("SCRAPER MULTI-SITES")
    logger.info("=" * 70)
    logger.info(f"Nombre de profils à scraper : {len(profiles_to_scrape)}")
    if args.max_pages:
        logger.info(f"Limitation : {args.max_pages} pages maximum par profil")

    all_job_offers = []
    scrapers_instances = []  # pour le finally

    # Ouvrir la connexion DB avant le scraping
    db = DatabaseManager()
    db.connect()
    db.create_table()

    try:
        # Scraping pour chaque profil
        for i, profile in enumerate(profiles_to_scrape, 1):
            logger.info(f"\n{'=' * 70}")
            logger.info(f"Profil {i}/{len(profiles_to_scrape)}")
            logger.info(f"{'=' * 70}")
            logger.info(f"Profil : {profile['label']} — {profile['url']}")

            # Déterminer le scraper à utiliser selon le site
            site = profile.get("site", "hellowork")
            scraper_class = SCRAPER_REGISTRY.get(site)
            if not scraper_class:
                logger.error(f"Site inconnu: {site}. Skipping profile.")
                continue

            # Instancier le scraper (headless = not args.visible)
            scraper = scraper_class(headless=not args.visible)
            scrapers_instances.append(scraper)

            # Scraping complet : recherche + détails (avec vérification DB)
            logger.info(f"Lancement du scraping avec {site}...")
            job_offers = scraper.scrape_search_with_details(
                profile['url'],
                max_pages=args.max_pages,
                db_manager=db,
                rescrape_existing=args.rescrape_existing
            )

            # Compter les offres nouvelles vs connues
            new_count = sum(1 for offer in job_offers if offer.new_offer)
            known_count = sum(1 for offer in job_offers if not offer.new_offer)
            logger.info(f"{len(job_offers)} offres trouvées : {new_count} nouvelles, {known_count} déjà en base")
            all_job_offers.extend(job_offers)

            # Pause entre les profils
            if i < len(profiles_to_scrape):
                logger.info("Pause de 5 secondes avant la prochaine URL...")
                import time
                time.sleep(5)

        logger.info(f"\n{'=' * 70}")
        logger.info(f"TOTAL : {len(all_job_offers)} offres collectées")
        logger.info(f"{'=' * 70}")

        # Affichage du résumé
        print_summary(all_job_offers)

        # Génération des noms de fichiers avec timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_file = OUTPUT_DIR / f"job_offers_{timestamp}.csv"
        json_file = OUTPUT_DIR / f"job_offers_{timestamp}.json"

        # Marquer les offres connues comme "not new" dans la base avant l'insertion
        known_urls = [offer.url for offer in all_job_offers if not offer.new_offer]
        if known_urls:
            db.mark_known_offers_not_new(known_urls)

        # Update last_seen_at for all scraped offers
        all_scraped_urls = [offer.url for offer in all_job_offers]
        db.update_last_seen(all_scraped_urls)

        # Mark offers as inactive if not seen in 7 days
        inactive_count = db.mark_inactive_if_unseen(days=7)

        # Export des données
        logger.info("\n" + "=" * 70)
        logger.info("EXPORT DES DONNÉES")
        logger.info("=" * 70)

        save_to_csv(all_job_offers, str(csv_file))
        save_to_json(all_job_offers, str(json_file))

        if args.rescrape_existing:
            db.mark_known_offers_not_new([o.url for o in all_job_offers])
            db.upsert_job_offers(all_job_offers)
            logger.info("Mode rescrape : upsert effectué en base pour toutes les offres")
        else:
            save_to_postgres(all_job_offers)

        logger.info(f"\nFichiers générés :")
        logger.info(f"  - CSV : {csv_file.absolute()}")
        logger.info(f"  - JSON: {json_file.absolute()}")

        # Bilan des offres nouvelles vs connues (avec déduplication)
        total_new = sum(1 for offer in all_job_offers if offer.new_offer)
        total_known = sum(1 for offer in all_job_offers if not offer.new_offer)
        unique_urls = len(set(offer.url for offer in all_job_offers))
        logger.info(f"\nBilan final :")
        logger.info(f"  - {total_new} nouvelles offres scrapées")
        logger.info(f"  - {total_known} offres déjà en base (non scrapées)")
        logger.info(f"  - {len(all_job_offers)} offres trouvées au total")
        logger.info(f"  - {unique_urls} offres uniques (après déduplication)")
        if inactive_count > 0:
            logger.info(f"  - {inactive_count} offres marquées comme inactives (non vues depuis 7 jours)")

        logger.info("\n" + "=" * 70)
        logger.info("SCRAPING TERMINÉ AVEC SUCCÈS")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"Erreur lors du scraping : {e}")
        import traceback
        traceback.print_exc()
        raise

    finally:
        # Fermer tous les scrapers instanciés
        for scraper in scrapers_instances:
            try:
                scraper.close()
            except Exception as e:
                logger.warning(f"Erreur lors de la fermeture d'un scraper: {e}")
        db.close()
        logger.info("Scrapers et base de données fermés proprement")


if __name__ == "__main__":
    main()
