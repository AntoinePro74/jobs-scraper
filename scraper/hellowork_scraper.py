#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Scraper pour le site HelloWork.
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import logging
from typing import List, Dict, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Importations des modules internes
from scraper.models.job_offer import JobOffer, EmploymentType, RemoteWorkType
from scraper.parsers.job_details_parser import JobDetailsParser
from .base_scraper import BaseScraper


class HelloWorkScraper(BaseScraper):
    """
    Scraper HelloWork héritant de BaseScraper.

    Implémente les méthodes spécifiques à HelloWork pour la pagination
    et l'extraction des offres.
    """

    def __init__(self, headless: bool = True):
        """
        Initialise le scraper HelloWork.

        Args:
            headless (bool): Si True, exécute Chrome en mode headless
        """
        # Appeler le constructeur de BaseScraper
        super().__init__(
            source_name="hellowork",
            base_url="https://www.hellowork.com",
            headless=headless
        )

        # Session requests pour les requêtes HTTP (si nécessaire)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def _get_total_pages(self, search_url: str) -> int:
        """
        Récupère le nombre total de pages de résultats.

        Args:
            search_url (str): URL de recherche HelloWork

        Returns:
            int: Nombre total de pages
        """
        try:
            self._setup_driver()
            self.driver.get(search_url)
            time.sleep(5)

            # Chercher l'indicateur "X offres" dans la page
            html = self.driver.page_source
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')

            # Chercher le texte contenant "offres" ou "offre"
            for el in soup.find_all(['p', 'span', 'div', 'button']):
                text = el.get_text(strip=True)
                if 'offres' in text.lower() or 'offre' in text.lower():
                    # Extraire le nombre avec regex
                    import re
                    match = re.search(r'(\d+)\s*offres?', text, re.IGNORECASE)
                    if match:
                        total_offers = int(match.group(1))
                        # 30 offres par page
                        total_pages = (total_offers + 29) // 30
                        self.logger.info(f"Nombre total d'offres: {total_offers}, pages: {total_pages}")
                        return max(1, total_pages)

            # Par défaut, retourner 1 page si non trouvé
            return 1

        except Exception as e:
            self.logger.warning(f"Erreur lors de la détection du nombre de pages: {e}")
            return 1

    def _build_page_url(self, base_url: str, page: int) -> str:
        """
        Construit l'URL d'une page spécifique.

        Args:
            base_url: URL de base de recherche
            page: Numéro de page (1-indexé)

        Returns:
            URL complète de la page
        """
        import re
        # Si l'URL contient déjà un paramètre p=, le remplacer
        if re.search(r'[?&]p=\d+', base_url):
            return re.sub(r'([?&]p=)\d+', f'\\g<1>{page}', base_url)
        # Sinon, ajouter le paramètre
        separator = '&' if '?' in base_url else '?'
        return f"{base_url}{separator}p={page}"

    def scrape_search_results(self, search_url: str, max_pages: Optional[int] = None) -> List[Dict]:
        """
        Scrape les offres d'emploi à partir d'une URL de recherche spécifique.
        Gère automatiquement la pagination.

        Args:
            search_url (str): URL de recherche HelloWork
            max_pages (Optional[int]): Nombre maximum de pages à scraper (None = toutes)

        Returns:
            List[Dict]: Liste des offres avec titre et lien
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
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

                # Attendre un peu supplémentaire pour que le JavaScript se charge
                time.sleep(5)

                # Trouver tous les éléments contenant les offres
                job_elements = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/emplois/']")

                self.logger.info(f"Trouvé {len(job_elements)} éléments avec '/emplois/' dans l'href")

                # Extraire les titres et liens
                for i, link_element in enumerate(job_elements):
                    try:
                        # Récupérer le titre de l'offre (textContent fonctionne mieux que .text)
                        raw_title = link_element.get_attribute("textContent")
                        # Nettoyer le titre : supprimer les espaces/sauts de ligne multiples
                        title = " ".join(raw_title.split()).strip()

                        # Récupérer l'URL
                        relative_url = link_element.get_attribute("href")

                        # Construire l'URL complète
                        if relative_url and relative_url.startswith("/"):
                            full_url = f"https://www.hellowork.com{relative_url}"
                        else:
                            full_url = relative_url

                        # Ajouter à la liste si le titre n'est pas vide et contient du texte pertinent
                        if title and len(title) > 3:  # Filtrer les titres trop courts
                            all_jobs.append({
                                "title": title,
                                "url": full_url
                            })
                            self.logger.debug(f"Ajouté [{i}]: {title} - {full_url}")

                    except Exception as e:
                        self.logger.warning(f"Erreur lors de l'extraction d'une offre: {e}")
                        continue

                # Pause entre les pages
                if page < total_pages:
                    time.sleep(2)

            except Exception as e:
                self.logger.error(f"Erreur lors du scraping de la page {page}: {e}")
                import traceback
                traceback.print_exc()
                continue

        # Filtrer les doublons (une offre peut apparaître sur plusieurs pages)
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
        Scrape les détails complets pour une liste d'offres d'emploi.

        Args:
            job_offers (List[Dict]): Liste des offres avec titre et URL

        Returns:
            List[JobOffer]: Liste des offres avec tous les détails
        """
        self.logger.info(f"Scraping des détails pour {len(job_offers)} offres")

        # Configurer le driver si nécessaire
        self._setup_driver()

        # Initialiser le parseur
        parser = JobDetailsParser(self.driver)

        detailed_offers = []

        for i, job_dict in enumerate(job_offers):
            try:
                self.logger.info(f"Traitement de l'offre {i+1}/{len(job_offers)}: {job_dict['title']}")

                # Créer un objet JobOffer à partir du dictionnaire
                job_offer = JobOffer(
                    title=job_dict['title'],
                    url=job_dict['url']
                )

                # Parser les détails
                detailed_offer = parser.parse_job_details(job_offer)
                detailed_offers.append(detailed_offer)

                # Pause pour éviter de surcharger le serveur
                time.sleep(2)

            except Exception as e:
                self.logger.error(f"Erreur lors du scraping des détails pour {job_dict['title']}: {e}")
                # Ajouter l'offre même si le scraping des détails a échoué
                detailed_offers.append(JobOffer(
                    title=job_dict['title'],
                    url=job_dict['url']
                ))
                continue

        self.logger.info(f"{len(detailed_offers)} offres traitées avec leurs détails")
        return detailed_offers

    def close(self):
        """
        Ferme proprement le driver Selenium et la session HTTP.
        Surcharge BaseScraper.close() pour fermer aussi la session requests.
        """
        super().close()  # Ferme le driver Selenium
        self.session.close()
        self.logger.info("Scraper fermé proprement")


    def save_to_csv(self, job_offers: List[JobOffer], filename: str = "job_offers_detailed.csv"):
        """
        Sauvegarde les offres dans un fichier CSV.

        Args:
            job_offers (List[JobOffer]): Liste des offres à sauvegarder
            filename (str): Nom du fichier de sortie
        """
        try:
            # Convertir les objets JobOffer en dictionnaires
            data = [offer.to_dict() for offer in job_offers]

            # Créer le DataFrame
            df = pd.DataFrame(data)

            # Sauvegarder en CSV
            df.to_csv(filename, index=False)
            self.logger.info(f"{len(job_offers)} offres sauvegardées dans {filename}")

        except Exception as e:
            self.logger.error(f"Erreur lors de la sauvegarde des données: {e}")

