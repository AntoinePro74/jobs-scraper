#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Parseur des détails d'offres d'emploi pour Welcome To The Jungle.

Extrait les informations d'une page d'offre WTTJ et enrichit un objet JobOffer.
Sélecteurs basés sur l'analyse du DOM WTTJ (mars 2026).
"""

import logging
import re
import time
from datetime import datetime
from typing import Optional
from bs4 import BeautifulSoup, Tag

from scraper.models.job_offer import JobOffer, EmploymentType, RemoteWorkType


class WTTJJobDetailsParser:
    """
    Parseur pour les offres Welcome To The Jungle.

    Utilise Selenium driver pour charger la page, puis BeautifulSoup pour
    extraire les champs selon des sélecteurs CSS spécifiques.

    Attributes:
        driver: Instance du driver Selenium (déjà initialisée)
        logger: Logger spécifique au parseur
    """

    def __init__(self, driver):
        """
        Initialise le parseur WTTJ.

        Args:
            driver: Instance Selenium WebDriver déjà configurée
        """
        self.driver = driver
        self.logger = logging.getLogger(f"{__name__}.wttj_parser")

    def parse_job_details(self, job_offer: JobOffer) -> JobOffer:
        """
        Extrait tous les détails de l'offre depuis la page chargée.

        Args:
            job_offer: Objet JobOffer avec au moins l'URL définie.
                       Les autres champs (title) servent de fallback.

        Returns:
            JobOffer enrichi avec tous les champs disponibles.
        """
        try:
            # Charger la page
            self.driver.get(job_offer.url)
            time.sleep(3)  # Attendre le rendu React/JS

            # Parser le HTML
            html = self.driver.page_source
            soup = BeautifulSoup(html, 'lxml')

            # Extraction séquentielle avec fallbacks
            job_offer.title = self._extract_title(soup) or job_offer.title
            job_offer.company = self._extract_company(soup)
            job_offer.description = self._extract_description(soup)
            job_offer.date_posted = self._extract_date(soup)
            job_offer.employment_type = self._extract_employment_type(soup)
            job_offer.location = self._extract_location(soup)
            job_offer.remote_work = self._extract_remote_work(soup)
            job_offer.salary = self._extract_salary(soup)
            job_offer.source = "wttj"

            self.logger.info(f"Détails extraits pour: {job_offer.title}")
            return job_offer

        except Exception as e:
            self.logger.error(f"Erreur lors du parsing des détails pour {job_offer.url}: {e}")
            raise

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Extrait le titre de l'offre.

        Sélecteur: première balise <h1> de la page ; sinon premier <h2>.
        Ne PAS filtrer par classe CSS.

        Args:
            soup: Objet BeautifulSoup de la page

        Returns:
            Titre extrait ou None si non trouvé
        """
        try:
            h1 = soup.find('h1')
            if h1 and h1.get_text(strip=True):
                return h1.get_text(strip=True)

            h2 = soup.find('h2')
            if h2 and h2.get_text(strip=True):
                return h2.get_text(strip=True)

            return None
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'extraction du titre: {e}")
            return None

    def _extract_company(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Extrait le nom de l'entreprise.

        Sélecteur: <a href=regex("^/fr/companies/[^/]+$")> → premier <span> enfant direct.
        Ne PAS filtrer par classe CSS.

        Args:
            soup: Objet BeautifulSoup de la page

        Returns:
            Nom de l'entreprise ou None
        """
        try:
            # Trouver le lien vers la page entreprise
            company_link = soup.find('a', href=re.compile(r'^/fr/companies/[^/]+$'))
            if company_link:
                # Prendre le premier span enfant direct
                span = company_link.find('span', recursive=False)
                if span:
                    return span.get_text(strip=True)

                # Fallback: tout texte direct dans le lien
                text = company_link.get_text(strip=True)
                if text:
                    return text

            return None
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'extraction de l'entreprise: {e}")
            return None

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Extrait la description complète de l'offre.

        Agrège dans l'ordre avec labels séparateurs:
        - div[data-testid="job-section-description"] → "=== Descriptif du poste ==="
        - div[data-testid="job-section-experience"] → "=== Profil recherché ==="
        - div[data-testid="job-section-process"] → "=== Déroulement des entretiens ==="

        Args:
            soup: Objet BeautifulSoup de la page

        Returns:
            Description complète formatée ou None
        """
        try:
            sections = []

            # Mapping testid → label
            section_map = {
                "job-section-description": "=== Descriptif du poste ===",
                "job-section-experience": "=== Profil recherché ===",
                "job-section-process": "=== Déroulement des entretiens ===",
            }

            for testid, label in section_map.items():
                div = soup.find('div', {'data-testid': testid})
                if div:
                    section_text = div.get_text(strip=True, separator='\n')
                    sections.append(f"{label}\n{section_text}")

            if sections:
                return '\n\n'.join(sections)
            return None
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'extraction de la description: {e}")
            return None

    def _extract_date(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Extrait la date de publication.

        Sélecteur: <time datetime="ISO8601"> → convertir en JJ/MM/AAAA.

        Args:
            soup: Objet BeautifulSoup de la page

        Returns:
            Date au format JJ/MM/AAAA ou None
        """
        try:
            time_tag = soup.find('time', {'datetime': True})
            if time_tag:
                datetime_str = time_tag.get('datetime')
                if datetime_str:
                    # Parser le ISO8601
                    try:
                        dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                        return dt.strftime('%d/%m/%Y')
                    except ValueError:
                        # Fallback: essayer d'autres formats courants
                        for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
                            try:
                                dt = datetime.strptime(datetime_str, fmt)
                                return dt.strftime('%d/%m/%Y')
                            except ValueError:
                                continue
            return None
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'extraction de la date: {e}")
            return None

    def _extract_employment_type(self, soup: BeautifulSoup) -> EmploymentType:
        """
        Extrait le type de contrat.

        Sélecteur: svg[alt="Contract"] → remonter au parent div → extraire le text node.
        Mapping (insensible à la casse):
            "cdi" → CDI
            "cdd" → CDD
            "intérim" → INTERIM
            "freelance" → FREELANCE
            "stage" → STAGE
            "alternance" → ALTERNANCE
        Fallback: EmploymentType.UNKNOWN

        Args:
            soup: Objet BeautifulSoup de la page

        Returns:
            Enum EmploymentType
        """
        try:
            svg = soup.find('svg', {'alt': re.compile(r'Contract', re.IGNORECASE)})
            if svg:
                # Remonter au parent div
                parent_div = svg.find_parent('div')
                if parent_div:
                    text = parent_div.get_text(strip=True)
                    if text:
                        text_lower = text.lower()
                        if 'cdi' in text_lower:
                            return EmploymentType.CDI
                        elif 'cdd' in text_lower:
                            return EmploymentType.CDD
                        elif 'intérim' in text_lower or 'interim' in text_lower:
                            return EmploymentType.INTERIM
                        elif 'freelance' in text_lower:
                            return EmploymentType.FREELANCE
                        elif 'stage' in text_lower:
                            return EmploymentType.STAGE
                        elif 'alternance' in text_lower:
                            return EmploymentType.ALTERNANCE

            return EmploymentType.UNKNOWN
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'extraction du type de contrat: {e}")
            return EmploymentType.UNKNOWN

    def _extract_location(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Extrait la localisation.

        Utilise le même pattern que contrat/salaire/télétravail :
        svg[alt="Location"] → parent div → tous les <span> descendants avec texte.

        Args:
            soup: Objet BeautifulSoup de la page

        Returns:
            Chaîne de localisation (ex: "Paris, Lyon") ou None
        """
        try:
            # Trouver le bloc contenant l'icône Location
            location_block = self._find_tag_block(soup, "Location")
            if location_block:
                # Extraire uniquement les spans feuilles (sans span enfant)
                all_spans = location_block.find_all('span')
                cities = []
                for span in all_spans:
                    # Ne garder que les spans qui n'ont pas de span enfant
                    if not span.find('span'):
                        text = span.get_text(strip=True)
                        if text:  # Filtrer les spans vides
                            cities.append(text)

                if cities:
                    return ', '.join(cities)

            # Si le bloc n'est pas trouvé, logger un warning
            self.logger.warning("Bloc localisation (svg alt='Location') non trouvé")
            return None
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'extraction de la localisation: {e}")
            return None

    def _extract_remote_work(self, soup: BeautifulSoup) -> RemoteWorkType:
        """
        Extrait le type de télétravail.

        Sélecteur: svg[alt="Remote"] → remonter au parent div → premier <span> text.
        Mapping (insensible à la casse):
            "télétravail total" ou "full remote" → FULL
            "télétravail partiel" → PARTIAL
            "hybride" → HYBRID
            "pas de télétravail" ou "no remote" → NONE
        Présence du bloc sans correspondance → UNKNOWN
        Absence du bloc → NONE

        Args:
            soup: Objet BeautifulSoup de la page

        Returns:
            Enum RemoteWorkType
        """
        try:
            svg = soup.find('svg', {'alt': re.compile(r'Remote', re.IGNORECASE)})
            if svg:
                # Remonter au parent div
                parent_div = svg.find_parent('div')
                if parent_div:
                    # Prendre le premier span avec du texte
                    span = parent_div.find('span', string=True)
                    if span:
                        text = span.get_text(strip=True).lower()
                        if 'total' in text or 'full' in text:
                            return RemoteWorkType.FULL
                        elif 'partiel' in text or 'partial' in text:
                            return RemoteWorkType.PARTIAL
                        elif 'hybride' in text:
                            return RemoteWorkType.HYBRID
                        elif 'pas' in text or 'no' in text:
                            return RemoteWorkType.NONE
                        else:
                            return RemoteWorkType.UNKNOWN

            # Absence du bloc = NONE (par défaut)
            return RemoteWorkType.NONE
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'extraction du télétravail: {e}")
            return RemoteWorkType.UNKNOWN

    def _extract_salary(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Extrait le salaire proposé.

        Sélecteur: svg[alt="Salary"] → remonter au parent div → extraire tout le text.
        Supprimer le label "Salaire : " s'il est présent.
        Nettoyer les espaces multiples.

        Args:
            soup: Objet BeautifulSoup de la page

        Returns:
            Chaîne de salaire ou None
        """
        try:
            svg = soup.find('svg', {'alt': re.compile(r'Salary', re.IGNORECASE)})
            if svg:
                # Remonter au parent div
                parent_div = svg.find_parent('div')
                if parent_div:
                    text = parent_div.get_text(strip=True)
                    if text:
                        # Supprimer le label "Salaire :" ou "Salaire:"
                        text = re.sub(r'^Salaire\s*[:\-]\s*', '', text, flags=re.IGNORECASE)
                        # Nettoyer les espaces multiples
                        text = ' '.join(text.split())
                        return text if text else None
            return None
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'extraction du salaire: {e}")
            return None

    def _find_tag_block(self, soup: BeautifulSoup, svg_alt: str) -> Optional[Tag]:
        """
        Helper: trouve l'élément div parent contenant un SVG avec l'alt donné.

        Parcourt tous les éléments du DOM contenant un <svg alt=svg_alt>,
        retourne le parent div de ce svg.
        Ne PAS filtrer par classe CSS sur le div parent.

        Args:
            soup: Objet BeautifulSoup
            svg_alt: Attribut alt du SVG à chercher (ex: "Contract", "Remote", "Salary")

        Returns:
            Tag div parent ou None
        """
        try:
            svg = soup.find('svg', {'alt': re.compile(svg_alt, re.IGNORECASE)})
            if svg:
                return svg.find_parent('div')
            return None
        except Exception as e:
            self.logger.debug(f"Erreur dans _find_tag_block pour '{svg_alt}': {e}")
            return None
