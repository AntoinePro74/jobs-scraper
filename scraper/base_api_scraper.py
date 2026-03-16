#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Scraper de base abstrait pour les sources avec API REST.

Définit le squelette commun à tous les scrapers utilisant une API REST (pas Selenium) :
- Gestion de session requests
- Pipeline de scraping avec pagination gérée par l'API
- Intégration avec la base de données pour déduplication
- Méthodes abstraites à implémenter par chaque scraper spécifique
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
import requests

from scraper.models.job_offer import JobOffer


class BaseApiScraper(ABC):
    """
    Classe de base abstraite pour tous les scrapers API d'offres d'emploi.

    Fournit une structure commune pour le scraping avec requests,
    la gestion de la pagination (définie par chaque implémentation) et
    l'intégration avec la base de données.

    Attributes:
        source_name (str): Nom de la source (ex: "apec", "adzuna")
        base_url (str): URL de base de l'API
        headers (dict): Headers HTTP avec User-Agent réaliste
        session (requests.Session): Session HTTP (initialisée en lazy)
        logger: Logger spécifique à la source
    """

    def __init__(self, source_name: str, base_url: str):
        """
        Initialise le scraper avec une configuration de base.

        Args:
            source_name: Nom identifiant la source (pour logging)
            base_url: URL de base de l'API
        """
        self.source_name = source_name
        self.base_url = base_url
        self.session = None
        self.logger = logging.getLogger(f"{__name__}.{source_name}")

    def _setup_session(self):
        """
        Configure la session requests avec headers réalistes.

        Utilise un User-Agent Chrome 120.
        L'initialisation est lazy : ne crée la session que si self.session est None.
        """
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                              'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/html;q=0.9,*/*;q=0.8',
                'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0'
            })
            self.logger.info("Session requests initialisée")

    def close(self):
        """
        Ferme proprement la session requests et libère les ressources.

        Doit être appelé à la fin de l'utilisation du scraper.
        """
        if self.session:
            self.session.close()
            self.session = None
            self.logger.info("Session requests fermée")

    def scrape_search_with_details(
        self,
        search_url: str,
        max_pages: Optional[int] = None,
        db_manager=None,
        rescrape_existing: bool = False
    ) -> List[JobOffer]:
        """
        Pipeline complet de scraping : recherche + détails avec déduplication DB.

        Args:
            search_url: URL de recherche de l'API
            max_pages: Nombre maximum de pages à scraper (None = toutes)
            db_manager: Instance de DatabaseManager pour vérifier les URLs existantes
            rescrape_existing: Si True, force le re-scraping des détails pour toutes les offres

        Returns:
            Liste des JobOffer avec détails complets pour les nouvelles,
            et JobOffer minimaux (sans détails) pour les connues
        """
        # Étape 1 : Scraping des résultats de recherche (titre + URL)
        basic_offers = self.scrape_search_results(search_url, max_pages=max_pages)

        # Si pas de DB, scraper toutes les offres normalement
        if db_manager is None:
            self.logger.info("Aucun gestionnaire de base de données fourni, scraping complet")
            return self.scrape_job_details(basic_offers)

        # Avec DB : optimisation de la déduplication
        if rescrape_existing:
            # Force le re-scraping de toutes les offres
            self.logger.info("Mode rescrape : re-scraping de toutes les offres")
            return self.scrape_job_details(basic_offers)
        else:
            # Comportement par défaut : skip les détails des offres déjà en base
            all_urls = [j['url'] for j in basic_offers]
            existing_urls = db_manager.get_existing_urls(all_urls)

            new_offers_dicts = [j for j in basic_offers if j['url'] not in existing_urls]
            known_offers_dicts = [j for j in basic_offers if j['url'] in existing_urls]

            self.logger.info(
                f"{len(new_offers_dicts)} nouvelles offres à scraper, "
                f"{len(known_offers_dicts)} déjà en base (détails non scrapés)"
            )

            # Scraper les détails uniquement pour les nouvelles offres
            detailed_new = self.scrape_job_details(new_offers_dicts)

            # Créer des JobOffer minimaux pour les offres connues (sans scraper détails)
            known_job_offers = [
                JobOffer(title=j['title'], url=j['url'], new_offer=False)
                for j in known_offers_dicts
            ]

            return detailed_new + known_job_offers

    @abstractmethod
    def scrape_search_results(self, search_url: str, max_pages: Optional[int] = None) -> List[Dict]:
        """
        Scrape les résultats de recherche (liste des offres).

        Doit implémenter :
        - Gestion de la pagination spécifique à l'API
        - Extraction des titre + URL pour chaque offre
        - Retourne une liste de dict avec au moins 'title' et 'url'

        Args:
            search_url: URL de recherche de l'API
            max_pages: Limite optionnelle du nombre de pages

        Returns:
            Liste de dictionnaires représentant les offres de base
        """
        pass

    @abstractmethod
    def scrape_job_details(self, job_offers: List[Dict]) -> List[JobOffer]:
        """
        Scrape les détails complets d'une liste d'offres.

        Doit implémenter :
        - Appel API pour chaque URL d'offre
        - Extraction des champs : company, location, employment_type, remote_work,
          salary, description, date_posted
        - Création d'objets JobOffer avec tous les champs renseignés

        Args:
            job_offers: Liste des offres avec au moins 'title' et 'url'

        Returns:
            Liste d'objets JobOffer avec détails complets
        """
        pass
