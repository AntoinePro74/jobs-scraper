#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Scraper pour l'API Jobup.ch.
"""

import logging
import time
import json
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from urllib.parse import urlparse, parse_qs, quote
import requests
from bs4 import BeautifulSoup

from scraper.models.job_offer import JobOffer, EmploymentType, RemoteWorkType
from scraper.base_api_scraper import BaseApiScraper


class JobupScraper(BaseApiScraper):
    """
    Scraper Jobup héritant de BaseApiScraper.

    Utilise l'API REST Jobup pour récupérer les offres d'emploi.
    """

    # Mapping des types de contrat
    EMPLOYMENT_TYPE_MAP = {
        "FULL_TIME": EmploymentType.CDI,
        "PART_TIME": EmploymentType.CDI,
        "CONTRACTOR": EmploymentType.FREELANCE,
        "TEMPORARY": EmploymentType.CDD,
        "INTERN": EmploymentType.STAGE,
    }

    def __init__(self, headless: bool = True):
        """
        Initialise le scraper Jobup.
        """
        super().__init__(
            source_name="jobup",
            base_url="https://job-search-api.jobup.ch"
        )

    def _extract_search_params(self, search_url: str) -> Dict:
        """
        Parse l'URL frontend jobup et reconstruit les paramètres pour l'API.

        Exemple URL: https://www.jobup.ch/fr/emplois/?publication-date=7&region=36&region=37&sort-by=date&term=%22account%20manager%22
        """
        parsed = urlparse(search_url)
        query_params = parse_qs(parsed.query)

        # Term -> query
        query = query_params.get("term", [""])[0]

        # Regions -> regionIds (liste)
        region_ids = query_params.get("region", [])

        # Publication date -> calculate range
        pub_date_days = query_params.get("publication-date", [None])[0]
        date_from = None
        date_to = datetime.now().strftime("%Y-%m-%d 23:59:59")

        if pub_date_days:
            try:
                days = int(pub_date_days)
                date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d 00:00:00")
            except ValueError:
                self.logger.warning(f"Invalid publication-date: {pub_date_days}")

        # Sort-by -> sort
        sort = query_params.get("sort-by", ["date"])[0]

        return {
            "query": query,
            "regionIds": region_ids,
            "publicationDateFrom": date_from,
            "publicationDateTo": date_to,
            "sort": sort,
            "rows": 20,
            "start": 0
        }

    def _build_api_url(self, params: Dict) -> str:
        """
        Construit l'URL de l'API de recherche Jobup avec encodage manuel.

        Ne JAMAIS utiliser params= de requests car il encode les espaces en '+',
        ce qui provoque des 404 sur l'API Jobup.
        """
        url = f"{self.base_url}/search?"
        parts = []

        for k, v in params.items():
            if v is None:
                continue
            if isinstance(v, list):
                for item in v:
                    parts.append(f"{k}={quote(str(item), safe='')}")
            else:
                parts.append(f"{k}={quote(str(v), safe='')}")

        return url + "&".join(parts)

    def scrape_search_results(
        self,
        search_url: str,
        max_pages: Optional[int] = None
    ) -> List[Dict]:
        """
        Scrape les résultats de recherche via l'API Jobup.
        """
        self.logger.info(f"Scraping des offres Jobup depuis: {search_url}")

        params = self._extract_search_params(search_url)
        self._setup_session()

        # Headers obligatoires pour éviter la 404
        jobup_headers = {
            "accept": "application/json",
            "accept-language": "fr",
            "origin": "https://www.jobup.ch",
            "referer": "https://www.jobup.ch/",
            "x-node-request": "false",
            "x-source": "jobup_ch_desktop",
        }
        self.session.headers.update(jobup_headers)

        all_offers = []
        page = 1
        total_count = None

        while True:
            try:
                # Mise à jour de la pagination
                params["start"] = len(all_offers)
                api_url = self._build_api_url(params)

                self.logger.info(f"Récupération page {page} (start={params['start']})")

                response = self.session.get(api_url, verify=False)
                response.raise_for_status()
                data = response.json()

                if total_count is None:
                    total_count = data.get("totalHits", 0)
                    self.logger.info(f"Total d'offres disponibles: {total_count}")

                documents = data.get("documents", [])
                if not documents:
                    self.logger.info("Aucun résultat trouvé pour cette page")
                    break

                for doc in documents:
                    try:
                        job_id = doc.get("id")
                        if not job_id:
                            continue

                        url = f"https://www.jobup.ch/fr/emplois/detail/{job_id}/"

                        basic_offer = {
                            "title": doc.get("title", "").strip(),
                            "url": url,
                            "company": doc.get("company", {}).get("name"),
                            "location": doc.get("place"),
                            "date_posted": doc.get("publicationDate"),
                        }

                        if basic_offer["title"] and basic_offer["url"]:
                            all_offers.append(basic_offer)
                    except Exception as e:
                        self.logger.warning(f"Erreur lors de l'extraction d'une offre: {e}")

                if len(all_offers) >= total_count:
                    break
                if max_pages is not None and page >= max_pages:
                    break

                page += 1
                time.sleep(0.3)

            except Exception as e:
                self.logger.error(f"Erreur lors du scraping page {page}: {e}")
                break

        return all_offers

    def scrape_job_details(self, job_offers: List[Dict]) -> List[JobOffer]:
        """
        Scrape les détails complets d'une liste d'offres Jobup.
        """
        self.logger.info(f"Scraping des détails pour {len(job_offers)} offres")
        self._setup_session()

        detailed_offers = []

        for i, job_dict in enumerate(job_offers):
            try:
                self.logger.info(f"Traitement de l'offre {i+1}/{len(job_offers)}: {job_dict['title']}")

                response = self.session.get(job_dict['url'])
                response.raise_for_status()

                scripts = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', response.text, re.DOTALL)
                detail = None
                for s in scripts:
                    try:
                        data = json.loads(s.strip())
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if item.get("@type") == "JobPosting":
                                detail = item
                                break
                        if detail:
                            break
                    except json.JSONDecodeError:
                        continue

                if not detail:
                    raise ValueError("Aucun JobPosting trouvé dans ld+json")

                # Company
                company = detail.get("hiringOrganization", {}).get("name") if isinstance(detail.get("hiringOrganization"), dict) else None
                if not company:
                    company = job_dict.get("company")

                # Location
                location = None
                loc_data = detail.get("jobLocation")
                if isinstance(loc_data, dict):
                    addr = loc_data.get("address")
                    if isinstance(addr, dict):
                        location = addr.get("addressLocality")
                if not location:
                    location = job_dict.get("location")

                # Description
                desc_html = detail.get("description")
                description = None
                if desc_html:
                    desc_soup = BeautifulSoup(desc_html, 'lxml')
                    description = desc_soup.get_text(strip=True, separator=' ')

                # Employment Type
                emp_type_raw = detail.get("employmentType")
                if isinstance(emp_type_raw, list) and emp_type_raw:
                    emp_type_raw = emp_type_raw[0]
                employment_type = self.EMPLOYMENT_TYPE_MAP.get(emp_type_raw, EmploymentType.UNKNOWN) if emp_type_raw else EmploymentType.UNKNOWN

                # Date
                date_posted_raw = detail.get("datePosted") or job_dict.get("date_posted")
                date_published = None
                if date_posted_raw:
                    try:
                        # "2026-04-23T01:42:26+02:00" -> "23/04/2026"
                        date_part = date_posted_raw.split("T")[0]
                        year, month, day = date_part.split("-")
                        date_published = f"{day}/{month}/{year}"
                    except Exception:
                        date_published = None

                job_offer = JobOffer(
                    title=job_dict["title"],
                    url=job_dict["url"],
                    company=company,
                    location=location,
                    description=description,
                    employment_type=employment_type,
                    remote_work=RemoteWorkType.UNKNOWN,
                    salary=None,
                    date_posted=date_published,
                    source=self.source_name,
                    new_offer=True
                )

                detailed_offers.append(job_offer)
                time.sleep(0.5)

            except Exception as e:
                self.logger.warning(f"Erreur lors du scraping des détails pour {job_dict['title']}: {e}")
                detailed_offers.append(JobOffer(
                    title=job_dict["title"],
                    url=job_dict["url"],
                    source=self.source_name,
                    new_offer=True
                ))
                continue

        return detailed_offers
