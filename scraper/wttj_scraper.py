#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Scraper pour le site Welcome To The Jungle utilisant l'API Algolia.
"""

import logging
import requests
import re
from urllib.parse import urlparse, parse_qs
from typing import List, Dict, Optional
from scraper.models.job_offer import JobOffer, EmploymentType, RemoteWorkType
from scraper.parsers.wttj_job_details_parser import WTTJJobDetailsParser
from .base_scraper import BaseScraper

class WttjScraper(BaseScraper):
    """
    Scraper Welcome To The Jungle basé sur l'API Algolia.
    """

    def __init__(self, headless: bool = True):
        super().__init__(
            source_name="wttj",
            base_url="https://www.welcometothejungle.com",
            headless=headless
        )
        self.algolia_app_id = "CSEKHVMS53"
        self.algolia_api_key = "4bd8f6215d0cc52b26430765769e65a0"
        self.algolia_index = "wttj_jobs_production_fr"
        self._init_algolia_credentials()

    def _init_algolia_credentials(self):
        """Récupère les clés Algolia dynamiquement depuis /api/env."""
        try:
            response = requests.get(f"{self.base_url}/api/env", timeout=10)
            if response.status_code == 200:
                text = response.text
                app_id = re.search(r'PUBLIC_ALGOLIA_APPLICATION_ID["\s:]+([A-Z0-9]+)', text)
                api_key = re.search(r'PUBLIC_ALGOLIA_API_KEY_CLIENT["\s:]+([a-f0-9]+)', text)

                if app_id:
                    self.algolia_app_id = app_id.group(1)
                if api_key:
                    self.algolia_api_key = api_key.group(1)

                if app_id or api_key:
                    self.logger.info("Identifiants Algolia mis à jour dynamiquement via regex")
        except Exception as e:
            self.logger.warning(f"Impossible de récupérer les clés Algolia dynamiquement, utilisation des fallbacks: {e}")

    def _parse_wttj_url_to_algolia(self, search_url: str) -> Dict:
        """
        Convertit une URL de recherche WTTJ en paramètres de requête Algolia.
        Exemple: https://www.welcometothejungle.com/fr/jobs?query="Account Manager"
        """
        parsed_url = urlparse(search_url)
        params = parse_qs(parsed_url.query)

        algolia_params = {
            "query": params.get("query", [""])[0].strip('"'),
            "filters": "",
            "page": 0
        }

        filters = []

        # Mapping des filtres URL -> Algolia
        # contract_type: refinementList[contract_type][]
        contract_types = params.get("refinementList[contract_type][]", [])
        if contract_types:
            # Algolia syntax: contract_type:"full_time"
            filters.append(f'contract_type:{" OR ".join([f"\"{ct}\"" for ct in contract_types])}')

        # country_code: refinementList[offices.country_code][]
        country_codes = params.get("refinementList[offices.country_code][]", [])
        if country_codes:
            filters.append(f'offices.country_code:{" OR ".join([f"\"{cc}\"" for cc in country_codes])}')

        # remote: refinementList[remote][]
        remotes = params.get("refinementList[remote][]", [])
        if remotes:
            filters.append(f'remote:{" OR ".join([f"\"{r}\"" for r in remotes])}')

        if filters:
            algolia_params["filters"] = " AND ".join(filters)

        return algolia_params

    def _get_total_pages(self, search_url: str) -> int:
        """
        Détermine le nombre total de pages via l'API Algolia.
        Note: Cette méthode est appelée par BaseScraper.
        """
        try:
            algolia_params = self._parse_wttj_url_to_algolia(search_url)
            results = self._call_algolia_api(algolia_params)
            return results.get("nbPages", 1)
        except Exception as e:
            self.logger.error(f"Erreur lors de la récupération du nombre de pages: {e}")
            return 1

    def _build_page_url(self, base_url: str, page: int) -> str:
        """
        Non utilisé directement par l'API Algolia, mais requis par BaseScraper.
        On retourne l'URL originale car la pagination est gérée dans Algolia params.
        """
        return base_url

    def _call_algolia_api(self, params: Dict) -> Dict:
        """Effectue l'appel POST vers l'API Algolia."""
        endpoint = f"https://{self.algolia_app_id}-dsn.algolia.net/1/indexes/{self.algolia_index}/query"

        headers = {
            "X-Algolia-Application-Id": self.algolia_app_id,
            "X-Algolia-API-Key": self.algolia_api_key,
            "Content-Type": "application/json",
            "Referer": "https://www.welcometothejungle.com/",
            "Origin": "https://www.welcometothejungle.com"
        }

        response = requests.post(endpoint, json=params, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()

    def scrape_search_results(self, search_url: str, max_pages: Optional[int] = None) -> List[Dict]:
        """
        Scrape les offres via l'API Algolia.
        """
        self.logger.info(f"Scraping WTTJ via Algolia API: {search_url}")

        algolia_params = self._parse_wttj_url_to_algolia(search_url)

        # Obtenir le total des pages
        try:
            # On fait un premier appel pour avoir nbPages
            initial_res = self._call_algolia_api(algolia_params)
            total_pages = initial_res.get("nbPages", 1)
        except Exception as e:
            self.logger.error(f"Erreur appel initial Algolia: {e}")
            return []

        if max_pages is not None:
            total_pages = min(total_pages, max_pages)

        self.logger.info(f"Total pages détectées: {total_pages}")

        all_jobs = []

        # Algolia pages start at 0
        for page in range(total_pages):
            self.logger.info(f"=== Page {page + 1}/{total_pages} ===")
            algolia_params["page"] = page

            try:
                res = self._call_algolia_api(algolia_params)
                hits = res.get("hits", [])

                for hit in hits:
                    # Construction de l'URL de l'offre
                    # La structure réelle du hit est hit["organization"]["slug"] et hit["slug"]
                    company_slug = hit.get("organization", {}).get("slug")
                    job_slug = hit.get("slug")

                    if company_slug and job_slug:
                        full_url = f"{self.base_url}/fr/companies/{company_slug}/jobs/{job_slug}"
                    else:
                        full_url = None

                    if full_url:
                        all_jobs.append({
                            "title": hit.get("name", "Titre inconnu"),
                            "url": full_url
                        })

                self.logger.info(f"Page {page + 1}: {len(hits)} offres collectées")

            except Exception as e:
                self.logger.error(f"Erreur lors du scraping de la page {page}: {e}")
                continue

        self.logger.info(f"{len(all_jobs)} offres extraites au total via Algolia")
        return all_jobs

    def scrape_job_details(self, job_offers: List[Dict]) -> List[JobOffer]:
        """
        Scrape les détails complets.
        On utilise requests + BeautifulSoup au lieu de Selenium pour plus de rapidité.
        """
        self.logger.info(f"Scraping des détails pour {len(job_offers)} offres")

        # On n'a plus besoin de driver Selenium pour WTTJ
        detailed_offers = []

        # On instancie le parser qui doit maintenant accepter du HTML
        parser = WTTJJobDetailsParser()

        for i, job_dict in enumerate(job_offers, 1):
            try:
                self.logger.info(f"[{i}/{len(job_offers)}] Traitement: {job_dict['title']}")

                job_offer = JobOffer(
                    title=job_dict['title'],
                    url=job_dict['url'],
                    source="wttj"
                )

                # Récupération du HTML via requests
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://www.welcometothejungle.com/",
                }
                response = requests.get(job_offer.url, headers=headers, timeout=10)
                response.raise_for_status()

                # On passe le HTML au parser
                detailed_offer = parser.parse_job_details(job_offer, response.text)
                detailed_offers.append(detailed_offer)

                # Pause légère pour éviter le ban
                import time
                time.sleep(1)

            except Exception as e:
                self.logger.error(f"Erreur lors du scraping des détails pour {job_dict['title']}: {e}")
                minimal_offer = JobOffer(
                    title=job_dict['title'],
                    url=job_dict['url'],
                    source="wttj"
                )
                detailed_offers.append(minimal_offer)
                continue

        return detailed_offers

    def close(self):
        """Nettoyage. On ne ferme rien car pas de driver Selenium."""
        pass
