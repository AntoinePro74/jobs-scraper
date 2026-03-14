#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Scraper pour le site Welcome To The Jungle.

Hérite de BaseScraper et implémente les méthodes spécifiques à WTTJ
pour la pagination et l'extraction des offres.
"""

import re
import time
import logging
from typing import List, Dict, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup

from scraper.models.job_offer import JobOffer
from scraper.parsers.wttj_job_details_parser import WTTJJobDetailsParser
from .base_scraper import BaseScraper


class WttjScraper(BaseScraper):
    """
    Scraper Welcome To The Jungle héritant de BaseScraper.

    Implémente les méthodes spécifiques à WTTJ pour la pagination
    et l'extraction des offres.
    """

    def __init__(self, headless: bool = True):
        """
        Initialise le scraper WTTJ.

        Args:
            headless (bool): Si True, exécute Chrome en mode headless
        """
        super().__init__(
            source_name="wttj",
            base_url="https://www.welcometothejungle.com",
            headless=headless
        )

    def _build_page_url(self, base_url: str, page: int) -> str:
        """
        Construit l'URL d'une page spécifique.

        Pour WTTJ : le paramètre est "page=N".
        Si "page=" existe déjà dans l'URL, le remplacer.
        Sinon, ajouter "&page=N" ou "?page=N" selon présence de "?".

        Args:
            base_url: URL de base de recherche
            page: Numéro de page (1-indexé)

        Returns:
            URL complète de la page
        """
        # Si l'URL contient déjà un paramètre page=, le remplacer
        if re.search(r'[?&]page=\d+', base_url):
            return re.sub(r'([?&]page=)\d+', f'\\g<1>{page}', base_url)
        # Sinon, ajouter le paramètre
        separator = '&' if '?' in base_url else '?'
        return f"{base_url}{separator}page={page}"

    def _get_total_pages(self, search_url: str) -> int:
        """
        Récupère le nombre total de pages de résultats.

        Sur WTTJ, le total est dans un élément avec data-testid="jobs-search-results-count".
        Attends que cet élément soit présent, extrait le nombre, et calcule le nb de pages.

        Args:
            search_url (str): URL de recherche WTTJ

        Returns:
            int: Nombre total de pages (minimum 1)
        """
        try:
            self._setup_driver()
            self.driver.get(search_url)

            # Attendre l'élément contenant le total (timeout 10s)
            try:
                wait = WebDriverWait(self.driver, 10)
                element = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-testid='jobs-search-results-count']"))
                )
                total_text = element.text.strip()
            except TimeoutException:
                self.logger.warning("Impossible de détecter le total (élément non trouvé), retour à 1 page")
                return 1

            # Supprimer les espaces (séparateurs de milliers) et convertir en int
            total_clean = total_text.replace(' ', '')
            try:
                total = int(total_clean)
                total_pages = (total + 29) // 30  # ceil division
                self.logger.info(f"Total offres détectées : {total}, soit {total_pages} pages")
                return max(1, total_pages)
            except ValueError:
                self.logger.warning(f"Valeur totale invalide: '{total_text}' (nettoyé: '{total_clean}'), retour à 1 page")
                return 1

        except Exception as e:
            self.logger.warning(f"Erreur lors de la détection du nombre de pages: {e}")
            return 1

    def scrape_search_results(self, search_url: str, max_pages: Optional[int] = None) -> List[Dict]:
        """
        Scrape les offres d'emploi à partir d'une URL de recherche WTTJ.

        Gère la pagination, attend le chargement des résultats,
        et extrait titre + URL de chaque offre.

        Args:
            search_url (str): URL de recherche WTTJ
            max_pages (Optional[int]): Nombre maximum de pages à scraper

        Returns:
            List[Dict]: Liste des offres avec au moins 'title' et 'url'
        """
        self.logger.info(f"Scraping des offres depuis l'URL: {search_url}")

        # Détecter le nombre total de pages
        total_pages = self._get_total_pages(search_url)

        # Limiter si max_pages est spécifié
        if max_pages is not None:
            total_pages = min(total_pages, max_pages)
            self.logger.info(f"Limitation à {max_pages} pages sur {total_pages} détectées")

        all_jobs = []

        for page in range(1, total_pages + 1):
            self.logger.info(f"=== Page {page}/{total_pages} ===")

            try:
                # Configurer le driver si nécessaire
                self._setup_driver()

                # Construire l'URL de la page courante
                page_url = self._build_page_url(search_url, page)
                self.driver.get(page_url)

                # Attendre le chargement des résultats
                wait = WebDriverWait(self.driver, 20)
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "ul[data-testid='search-results']")))

                # Attendre un peu supplémentaire pour que le JavaScript se charge
                time.sleep(3)

                # Parser avec BeautifulSoup
                html = self.driver.page_source
                soup = BeautifulSoup(html, 'lxml')

                # Trouver la liste des résultats
                results_ul = soup.find('ul', {'data-testid': 'search-results'})
                if not results_ul:
                    self.logger.warning(f"Pas de liste de résultats trouvée (ul[data-testid='search-results']) sur la page {page}")
                    continue

                # Itérer sur les <li>
                list_items = results_ul.find_all('li')
                self.logger.info(f"Trouvé {len(list_items)} éléments <li> dans les résultats")

                for i, li in enumerate(list_items):
                    try:
                        # Chercher le lien vers l'offre : <a href=regex("/fr/companies/.*/jobs/")>
                        link = li.find('a', href=re.compile(r'/fr/companies/.*/jobs/'))
                        if not link:
                            continue

                        href = link.get('href')
                        if not href:
                            continue

                        # Construire l'URL absolue
                        if href.startswith('/'):
                            full_url = f"{self.base_url}{href}"
                        else:
                            full_url = href

                        # Extraire le titre : premier <h2> enfant direct du <li>
                        title_h2 = li.find('h2')
                        if title_h2:
                            title = title_h2.get_text(strip=True)
                        else:
                            # Fallback sur aria-label du lien
                            title = link.get('aria-label')
                            if not title:
                                title = "Titre inconnu"
                            else:
                                title = title.strip()

                        if title and len(title) > 3 and full_url:
                            all_jobs.append({
                                'title': title,
                                'url': full_url
                            })
                            self.logger.debug(f"Ajouté [{i}]: {title} - {full_url}")

                    except Exception as e:
                        self.logger.warning(f"Erreur lors de l'extraction d'une offre (page {page}, item {i}): {e}")
                        continue

                self.logger.info(f"Page {page} : {len(all_jobs)} offres collectées jusqu'à présent")

            except Exception as e:
                self.logger.error(f"Erreur lors du scraping de la page {page}: {e}")
                import traceback
                traceback.print_exc()
                continue

        # Déduplication finale (une offre peut apparaître sur plusieurs pages)
        seen_urls = set()
        unique_jobs = []
        for job in all_jobs:
            if job['url'] not in seen_urls:
                seen_urls.add(job['url'])
                unique_jobs.append(job)

        self.logger.info(f"{len(unique_jobs)} offres uniques extraites au total")
        return unique_jobs

    def scrape_job_details(self, job_offers: List[Dict]) -> List[JobOffer]:
        """
        Scrape les détails complets pour une liste d'offres WTTJ.

        Utilise WTTJJobDetailsParser pour extraire les champs.
        Crée un JobOffer minimal pour chaque offre, puis enrichit.

        Args:
            job_offers (List[Dict]): Liste des offres avec 'title' et 'url'

        Returns:
            List[JobOffer]: Liste des offres avec détails complets
        """
        self.logger.info(f"Scraping des détails pour {len(job_offers)} offres")

        # Configurer le driver si nécessaire
        self._setup_driver()

        # Initialiser le parseur WTTJ
        parser = WTTJJobDetailsParser(self.driver)

        detailed_offers = []

        for i, job_dict in enumerate(job_offers, 1):
            try:
                self.logger.info(f"[{i}/{len(job_offers)}] Traitement: {job_dict['title']}")

                # Créer un JobOffer initial (source="wttj" sera écrasée par le parser si déjà défini)
                job_offer = JobOffer(
                    title=job_dict['title'],
                    url=job_dict['url'],
                    source="wttj"
                )

                # Parser les détails
                detailed_offer = parser.parse_job_details(job_offer)
                detailed_offers.append(detailed_offer)

                # Pause entre les offres
                if i < len(job_offers):
                    time.sleep(2)

            except Exception as e:
                self.logger.error(f"Erreur lors du scraping des détails pour {job_dict['title']}: {e}")
                # Ajouter l'offre minimale même en cas d'échec pour ne pas perdre la donnée
                minimal_offer = JobOffer(
                    title=job_dict['title'],
                    url=job_dict['url'],
                    source="wttj"
                )
                detailed_offers.append(minimal_offer)
                continue

        self.logger.info(f"{len(detailed_offers)} offres traitées avec leurs détails")
        return detailed_offers
