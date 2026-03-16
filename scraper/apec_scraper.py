#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Scraper pour l'API APEC (Association Pour l'Emploi des Cadres).
"""

import logging
import time
import json
from typing import List, Dict, Optional
from urllib.parse import urlparse, parse_qs
import requests
from bs4 import BeautifulSoup

from scraper.models.job_offer import JobOffer, EmploymentType, RemoteWorkType
from scraper.base_api_scraper import BaseApiScraper


class ApecScraper(BaseApiScraper):
    """
    Scraper APEC héritant de BaseApiScraper.

    Utilise l'API REST APEC pour récupérer les offres d'emploi cadres.
    """

    # Mapping des types de contrat
    EMPLOYMENT_TYPE_MAP = {
        101888: EmploymentType.CDI,
        101887: EmploymentType.CDD,
        101889: EmploymentType.INTERIM,
    }

    # Mapping des types de télétravail
    REMOTE_WORK_MAP = {
        20767: RemoteWorkType.FULL,
        20765: RemoteWorkType.HYBRID,
        20766: RemoteWorkType.OCCASIONAL,
    }

    def __init__(self):
        """
        Initialise le scraper APEC.
        """
        super().__init__(
            source_name="apec",
            base_url="https://www.apec.fr"
        )

    def _extract_search_params(self, search_url: str) -> Dict:
        """
        Extrait les paramètres de recherche depuis l'URL frontend APEC.

        Args:
            search_url: URL de recherche APEC (ex: https://www.apec.fr/candidat/recherche-emploi.html/emploi?motsCles=...)

        Returns:
            Dictionnaire des paramètres pour le payload API
        """
        parsed = urlparse(search_url)
        query_params = parse_qs(parsed.query)

        def to_list(value):
            """Convertit une valeur en liste si ce n'est pas déjà le cas."""
            if isinstance(value, list):
                return value
            return [value] if value else []

        # Construire le payload
        payload = {
            "motsCles": query_params.get("motsCles", [""])[0] or "",
            "typesContrat": to_list(query_params.get("typesContrat", [])),
            "typesTeletravail": to_list(query_params.get("typesTeletravail", [])),
            "fonctions": [],
            "lieux": [],
            "statutPoste": [],
            "niveauxExperience": [],
            "secteursActivite": [],
            "typeClient": "CADRE"
        }

        # Gérer le tri
        sort_type = query_params.get("sortsType", ["DATE"])[0]
        payload["sorts"] = [{"type": sort_type, "direction": "DESCENDING"}]

        # Initialiser la pagination
        payload["pagination"] = {"range": 20, "startIndex": 0}
        payload["activeFiltre"] = True

        return payload

    def _build_api_url(self) -> str:
        """
        Construit l'URL de l'API de recherche APEC.

        Returns:
            URL complète de l'API
        """
        return f"{self.base_url}/cms/webservices/rechercheOffre"

    def scrape_search_results(
        self,
        search_url: str,
        max_pages: Optional[int] = None
    ) -> List[Dict]:
        """
        Scrape les résultats de recherche via l'API APEC.

        Args:
            search_url: URL de recherche frontend APEC
            max_pages: Nombre maximum de pages à scraper (None = toutes)

        Returns:
            Liste de dictionnaires représentant les offres de base
        """
        self.logger.info(f"Scraping des offres APEC depuis: {search_url}")

        # Parser les paramètres de recherche
        payload = self._extract_search_params(search_url)
        self.logger.info(f"Paramètres extraits: {payload}")

        # Initialiser la session
        self._setup_session()

        all_offers = []
        page = 1
        total_count = None

        while True:
            try:
                # Mettre à jour startIndex pour la pagination
                payload["pagination"]["startIndex"] = len(all_offers)

                self.logger.info(
                    f"Récupération page {page} (startIndex={payload['pagination']['startIndex']})"
                )

                # Appel API POST
                response = self.session.post(
                    self._build_api_url(),
                    json=payload,
                    headers={'Content-Type': 'application/json'}
                )
                response.raise_for_status()

                data = response.json()

                # Extraire totalCount si pas encore fait
                if total_count is None:
                    total_count = data.get("totalCount", 0)
                    self.logger.info(f"Total d'offres disponibles: {total_count}")

                # Vérifier s'il y a des résultats
                if "resultats" not in data or not data["resultats"]:
                    self.logger.info("Aucun résultat trouvé pour cette page")
                    break

                # Extraire les offres de la page
                for offer in data["resultats"]:
                    try:
                        # Numéro de l'offre
                        numero_offre = offer.get("numeroOffre")
                        if not numero_offre:
                            self.logger.warning("Offre sans numeroOffre, ignorée")
                            continue

                        # Construire l'URL canonique
                        url = f"{self.base_url}/candidat/recherche-emploi.html/emploi/detail-offre/{numero_offre}"

                        # Extraire les champs pertinents pour la déduplication + mapping
                        basic_offer = {
                            "title": offer.get("intitule", "").strip(),
                            "url": url,
                            "salary": offer.get("salaireTexte"),
                            "date_posted": offer.get("datePublication"),
                            "_type_contrat": offer.get("typeContrat"),
                            "_teletravail": offer.get("idNomTeletravail")
                        }

                        # Vérifier que le titre et l'URL sont présents
                        if basic_offer["title"] and basic_offer["url"]:
                            all_offers.append(basic_offer)
                        else:
                            self.logger.warning(f"Offre incomplète, ignorée: {basic_offer}")

                    except Exception as e:
                        self.logger.warning(f"Erreur lors de l'extraction d'une offre: {e}")
                        continue

                self.logger.info(f"Total offres extraites jusqu'à maintenant: {len(all_offers)}")

                # Vérifier les conditions d'arrêt
                if len(all_offers) >= total_count:
                    self.logger.info(f"Toutes les offres collectées ({len(all_offers)}/{total_count})")
                    break

                if max_pages is not None and page >= max_pages:
                    self.logger.info(f"Limite max_pages atteinte ({max_pages} pages)")
                    break

                page += 1

                # Petite pause pour éviter de surcharger l'API
                time.sleep(0.2)

            except requests.RequestException as e:
                self.logger.error(f"Erreur réseau lors du scraping page {page}: {e}")
                break
            except json.JSONDecodeError as e:
                self.logger.error(f"Erreur de décodage JSON page {page}: {e}")
                break
            except Exception as e:
                self.logger.error(f"Erreur inattendue page {page}: {e}")
                import traceback
                traceback.print_exc()
                break

        # Déduplication par URL
        seen_urls = set()
        unique_offers = []
        for offer in all_offers:
            if offer["url"] not in seen_urls:
                seen_urls.add(offer["url"])
                unique_offers.append(offer)

        self.logger.info(f"{len(unique_offers)} offres uniques extraites au total")
        return unique_offers

    def scrape_job_details(self, job_offers: List[Dict]) -> List[JobOffer]:
        """
        Scrape les détails complets d'une liste d'offres via les APIs APEC.

        Args:
            job_offers: Liste des offres avec au moins 'title' et 'url'

        Returns:
            Liste d'objets JobOffer avec détails complets
        """
        self.logger.info(f"Scraping des détails pour {len(job_offers)} offres")
        self._setup_session()

        detailed_offers = []

        for i, job_dict in enumerate(job_offers):
            try:
                self.logger.info(f"Traitement de l'offre {i+1}/{len(job_offers)}: {job_dict['title']}")

                # Extraire le numeroOffre depuis l'URL
                # URL format: https://www.apec.fr/candidat/recherche-emploi.html/emploi/detail-offre/{numeroOffre}
                url_parts = job_dict['url'].rstrip('/').split('/')
                numero_offre = url_parts[-1]

                if not numero_offre:
                    self.logger.warning(f"Impossible d'extraire numeroOffre depuis {job_dict['url']}")
                    raise ValueError(" numeroOffre manquant")

                # Appel API détail
                detail_url = f"{self.base_url}/cms/webservices/offre/public?numeroOffre={numero_offre}"
                response = self.session.get(detail_url)
                response.raise_for_status()
                data = response.json()

                # Parser les données de détail
                offer_data = data

                # Company : nomCompteEtablissement (fallback: nomCommercial depuis la liste)
                company = offer_data.get("nomCompteEtablissement")
                if not company:
                    # Fallback sur les données de la liste si disponibles
                    company = job_dict.get("nomCommercial")
                if not company:
                    company = None

                # Location : lieux[0]["libelleLieu"] ou lieuTexte
                location = None
                lieux = offer_data.get("lieux", [])
                if lieux and isinstance(lieux, list) and len(lieux) > 0:
                    location = lieux[0].get("libelleLieu")
                if not location:
                    location = offer_data.get("lieuTexte")

                # Description : concaténation de plusieurs champs
                description_parts = []
                for field in [
                    "texteHtml",
                    "texteHtmlProfil",
                    "texteHtmlEntreprise",
                    "texteProcessRecrutement",
                    "textePresentation"
                ]:
                    html_content = offer_data.get(field)
                    if html_content:
                        soup = BeautifulSoup(html_content, 'lxml')
                        text = soup.get_text(strip=True, separator=' ')
                        if text:
                            description_parts.append(text)

                description = "\n\n---\n\n".join(description_parts) if description_parts else None

                # Mapping des types
                type_contrat_int = job_dict.get("_type_contrat")
                employment_type = self.EMPLOYMENT_TYPE_MAP.get(
                    type_contrat_int, EmploymentType.UNKNOWN
                ) if type_contrat_int is not None else EmploymentType.UNKNOWN

                teletravail_int = job_dict.get("_teletravail")
                remote_work = self.REMOTE_WORK_MAP.get(
                    teletravail_int, RemoteWorkType.UNKNOWN
                ) if teletravail_int is not None else RemoteWorkType.UNKNOWN

                # Date de publication : format "YYYY-MM-DDThh:mm:ss.000+0000" → "DD/MM/YYYY"
                date_published = job_dict.get("date_posted")
                if date_published:
                    try:
                        # Exemple: "2024-03-15T00:00:00.000+0000"
                        date_part = date_published.split("T")[0]
                        year, month, day = date_part.split("-")
                        date_published = f"{day}/{month}/{year}"
                    except Exception:
                        self.logger.warning(f"Format de date non reconnu: {date_published}")
                        date_published = None

                # Créer l'objet JobOffer
                job_offer = JobOffer(
                    title=job_dict["title"],
                    url=job_dict["url"],
                    company=company,
                    location=location,
                    description=description,
                    employment_type=employment_type,
                    remote_work=remote_work,
                    salary=job_dict.get("salary"),
                    date_posted=date_published,
                    source=self.source_name,
                    new_offer=True
                )

                detailed_offers.append(job_offer)

                # Respecter une pause entre chaque appel détail
                time.sleep(0.5)

            except requests.RequestException as e:
                self.logger.warning(f"Erreur réseau pour l'offre {job_dict['title']}: {e}")
                # Ajouter une offre minimale en cas d'erreur
                detailed_offers.append(JobOffer(
                    title=job_dict["title"],
                    url=job_dict["url"],
                    source=self.source_name,
                    new_offer=True
                ))
                continue
            except json.JSONDecodeError as e:
                self.logger.warning(f"Erreur JSON pour l'offre {job_dict['title']}: {e}")
                detailed_offers.append(JobOffer(
                    title=job_dict["title"],
                    url=job_dict["url"],
                    source=self.source_name,
                    new_offer=True
                ))
                continue
            except Exception as e:
                self.logger.warning(f"Erreur lors du scraping des détails pour {job_dict['title']}: {e}")
                detailed_offers.append(JobOffer(
                    title=job_dict["title"],
                    url=job_dict["url"],
                    source=self.source_name,
                    new_offer=True
                ))
                continue

        self.logger.info(f"{len(detailed_offers)} offres traitées avec leurs détails")
        return detailed_offers
