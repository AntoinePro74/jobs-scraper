"""
Parseur pour les détails des offres d'emploi HelloWork.

Sélecteurs validés via DevTools :
- TITRE       : span[data-cy="jobTitle"]
- ENTREPRISE  : a[href*="/fr-fr/entreprises/"]
- TAGS        : soup.find("ul", class_="tw-gap-3")
- SALAIRE     : button[data-cy="salary-tag-button"] span.tw-truncate
- DESCRIPTION : soup.find("div", class_="tw-gap-8")
- DATE        : soup.find("p", class_="tw-text-grey-500")
"""

import re
import logging
from typing import Optional, List
from bs4 import BeautifulSoup, Tag
from selenium.webdriver.remote.webdriver import WebDriver
from scraper.models.job_offer import JobOffer, EmploymentType, RemoteWorkType


class JobDetailsParser:
    """
    Parseur spécialisé pour extraire les détails d'une offre d'emploi HelloWork.
    Utilise BeautifulSoup pour une extraction plus robuste des éléments HTML.
    """

    # Constantes pour les types de contrat
    CONTRACT_TYPES = ["CDI", "CDD", "Intérim", "Freelance", "Stage", "Alternance"]

    def __init__(self, driver: WebDriver):
        """
        Initialise le parseur.

        Args:
            driver (WebDriver): Instance du driver Selenium
        """
        self.driver = driver
        self.logger = logging.getLogger(__name__)

    def parse_job_details(self, job_offer: JobOffer) -> JobOffer:
        """
        Parse les détails d'une offre d'emploi.

        Args:
            job_offer (JobOffer): Offre avec les informations de base

        Returns:
            JobOffer: Offre avec les détails complétés
        """
        try:
            # Accéder à la page de l'offre
            self.driver.get(job_offer.url)

            # Attendre le chargement de la page
            import time
            time.sleep(2)

            # Récupérer le HTML de la page et créer un objet BeautifulSoup
            html = self.driver.page_source
            soup = BeautifulSoup(html, 'lxml')

            # Extraire les détails avec les nouveaux sélecteurs
            job_offer.title = self._extract_title(soup) or job_offer.title
            job_offer.company = self._extract_company(soup)
            job_offer.location = self._extract_location(soup)
            job_offer.employment_type = self._extract_employment_type(soup)
            job_offer.remote_work = self._extract_remote_work(soup)
            job_offer.salary = self._extract_salary(soup)
            job_offer.description = self._extract_description(soup)
            job_offer.date_posted = self._extract_date(soup)

        except Exception as e:
            self.logger.error(f"Erreur lors du parsing des détails pour {job_offer.url}: {e}")

        return job_offer

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Extrait le titre de l'offre.

        Args:
            soup (BeautifulSoup): Objet BeautifulSoup de la page

        Returns:
            Optional[str]: Titre de l'offre ou None si non trouvé
        """
        try:
            title_element = soup.find("span", attrs={"data-cy": "jobTitle"})
            if title_element:
                return title_element.get_text(strip=True)
            return None
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'extraction du titre: {e}")
            return None

    def _extract_company(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Extrait le nom de l'entreprise.

        Args:
            soup (BeautifulSoup): Objet BeautifulSoup de la page

        Returns:
            Optional[str]: Nom de l'entreprise ou None si non trouvé
        """
        try:
            company_element = soup.find("a", href=re.compile(r"/fr-fr/entreprises/"))
            if company_element:
                return company_element.get_text(strip=True)
            return None
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'extraction de l'entreprise: {e}")
            return None

    def _extract_tags(self, soup: BeautifulSoup) -> List[str]:
        """
        Extrait tous les tags de l'offre (localisation, contrat, télétravail, expérience).

        Args:
            soup (BeautifulSoup): Objet BeautifulSoup de la page

        Returns:
            List[str]: Liste des tags extraits
        """
        try:
            tags_container = soup.find("ul", class_="tw-gap-3")
            if tags_container:
                return [li.get_text(strip=True) for li in tags_container.find_all("li")]
            return []
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'extraction des tags: {e}")
            return []

    def _extract_location(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Extrait la localisation de l'offre (premier tag).

        Args:
            soup (BeautifulSoup): Objet BeautifulSoup de la page

        Returns:
            Optional[str]: Localisations ou None si non trouvé
        """
        try:
            all_tags = self._extract_tags(soup)
            if len(all_tags) > 0:
                return all_tags[0]
            return None
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'extraction de la localisation: {e}")
            return None

    def _extract_employment_type(self, soup: BeautifulSoup) -> EmploymentType:
        """
        Extrait le type de contrat de l'offre.
        Cherche le premier tag contenant l'un des types de contrat connus.

        Args:
            soup (BeautifulSoup): Objet BeautifulSoup de la page

        Returns:
            EmploymentType: Type de contrat
        """
        try:
            all_tags = self._extract_tags(soup)
            for tag in all_tags:
                for contract_type in self.CONTRACT_TYPES:
                    if contract_type in tag:
                        return EmploymentType(contract_type)
            return EmploymentType.UNKNOWN
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'extraction du type de contrat: {e}")
            return EmploymentType.UNKNOWN

    def _extract_remote_work(self, soup: BeautifulSoup) -> RemoteWorkType:
        """
        Extrait les informations sur le télétravail.
        Cherche le premier tag contenant "Télétravail".

        Args:
            soup (BeautifulSoup): Objet BeautifulSoup de la page

        Returns:
            RemoteWorkType: Type de télétravail
        """
        try:
            all_tags = self._extract_tags(soup)
            for tag in all_tags:
                if "Télétravail" in tag:
                    # Déterminer le type de télétravail
                    if "complet" in tag.lower() or "100%" in tag:
                        return RemoteWorkType.FULL
                    elif "hybride" in tag.lower():
                        return RemoteWorkType.HYBRID
                    elif "partiel" in tag.lower():
                        return RemoteWorkType.PARTIAL
                    else:
                        return RemoteWorkType.UNKNOWN
            return RemoteWorkType.NONE
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'extraction du télétravail: {e}")
            return RemoteWorkType.UNKNOWN

    def _extract_experience(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Extrait le niveau d'expérience requis (premier tag contenant "Exp.").

        Args:
            soup (BeautifulSoup): Objet BeautifulSoup de la page

        Returns:
            Optional[str]: Niveau d'expérience ou None si non trouvé
        """
        try:
            all_tags = self._extract_tags(soup)
            for tag in all_tags:
                if "Exp." in tag:
                    return tag
            return None
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'extraction de l'expérience: {e}")
            return None

    def _extract_salary(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Extrait le salaire de l'offre.

        Args:
            soup (BeautifulSoup): Objet BeautifulSoup de la page

        Returns:
            Optional[str]: Salaire ou None si non trouvé
        """
        try:
            salary_button = soup.find("button", attrs={"data-cy": "salary-tag-button"})
            if salary_button:
                salary_span = salary_button.find("span", class_="tw-truncate")
                if salary_span:
                    salary_text = salary_span.get_text(strip=True)
                    if salary_text:
                        return salary_text
            return None
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'extraction du salaire: {e}")
            return None

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Extrait la description complète de l'offre.
        Récupère tous les paragraphes <p> dans le conteneur tw-gap-8.
        Plusieurs div peuvent avoir cette classe, on prend celui qui contient des paragraphes.

        Args:
            soup (BeautifulSoup): Objet BeautifulSoup de la page

        Returns:
            Optional[str]: Description complète ou None si non trouvée
        """
        try:
            # Trouver tous les conteneurs de description
            description_containers = soup.find_all("div", class_="tw-gap-8")

            # Prendre le premier conteneur qui contient des paragraphes
            for container in description_containers:
                paragraphs = container.find_all("p")
                if paragraphs:
                    # Joindre les paragraphes avec des sauts de ligne
                    description_parts = []
                    for p in paragraphs:
                        text = p.get_text(separator="\n", strip=True)
                        if text:  # Ignorer les paragraphes vides
                            description_parts.append(text)

                    if description_parts:
                        return "\n\n".join(description_parts)

            return None
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'extraction de la description: {e}")
            return None

    def _extract_date(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Extrait la date de publication de l'offre.

        Args:
            soup (BeautifulSoup): Objet BeautifulSoup de la page

        Returns:
            Optional[str]: Date de publication au format JJ/MM/AAAA ou None
        """
        try:
            date_element = soup.find("p", class_="tw-text-grey-500")
            if date_element:
                text = date_element.get_text(strip=True)
                # Extraire la date avec une regex
                match = re.search(r"Publiée le (\d{2}/\d{2}/\d{4})", text)
                if match:
                    return match.group(1)
            return None
        except Exception as e:
            self.logger.warning(f"Erreur lors de l'extraction de la date: {e}")
            return None
