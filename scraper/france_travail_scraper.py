#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Scraper pour l'API France Travail.
"""

import logging
import time
import json
import os
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs
import requests
from bs4 import BeautifulSoup

from scraper.models.job_offer import JobOffer, EmploymentType, RemoteWorkType
from scraper.base_api_scraper import BaseApiScraper


class FranceTravailScraper(BaseApiScraper):
    """
    Scraper France Travail héritant de BaseApiScraper.

    Utilise l'API REST France Travail (partenaire) pour récupérer les offres d'emploi.
    Authentification OAuth2 Client Credentials.
    """

    # Mapping des types de contrat selon la nomenclature France Travail
    EMPLOYMENT_TYPE_MAP = {
        "CDI": EmploymentType.CDI,
        "CDD": EmploymentType.CDD,
        "MIS": EmploymentType.INTERIM,  # Mission intérimaire
        "SAI": EmploymentType.INTERIM,  # Saisonnier
        "LIB": EmploymentType.FREELANCE,  # Libre profession
        "STG": EmploymentType.STAGE,
        "ALT": EmploymentType.ALTERNANCE,
    }

    # Mapping des types de télétravail
    REMOTE_WORK_MAP = {
        "FULL": RemoteWorkType.FULL,
        "HYB": RemoteWorkType.HYBRID,
        "PAR": RemoteWorkType.PARTIAL,
        "NON": RemoteWorkType.NONE,
    }

    # Endpoints d'authentification et API
    AUTH_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"
    API_BASE_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2"

    def __init__(self, headless: bool = True):
        """
        Initialise le scraper France Travail.

        Args:
            headless: Ignoré pour les API (présent pour compatibilité)
        """
        super().__init__(
            source_name="france_travail",
            base_url=self.API_BASE_URL
        )

        # Récupérer les identifiants depuis l'environnement
        self.client_id = os.getenv("FRANCE_TRAVAIL_CLIENT_ID")
        self.client_secret = os.getenv("FRANCE_TRAVAIL_CLIENT_SECRET")

        if not self.client_id or not self.client_secret:
            raise ValueError(
                "FRANCE_TRAVAIL_CLIENT_ID et FRANCE_TRAVAIL_CLIENT_SECRET "
                "doivent être définis dans les variables d'environnement"
            )

        # Cache du token OAuth2
        self._access_token = None
        self._token_expires_at = None

    def _get_auth_token(self) -> str:
        """
        Obtient un token OAuth2 via Client Credentials.

        Le token est mis en cache jusqu'à son expiration (généralement 1 heure).

        Returns:
            Token d'accès

        Raises:
            requests.RequestException: Si l'authentification échoue
        """
        if self.session is None:
            self._setup_session()
        # Vérifier si le token est encore valide
        if self._access_token and self._token_expires_at:
            if datetime.now() < self._token_expires_at:
                self.logger.debug("Réutilisation du token OAuth2 en cache")
                return self._access_token
            else:
                self.logger.info("Token expiré, demande d'un nouveau token")

        self.logger.info("Demande d'un nouveau token OAuth2 France Travail")

        try:
            response = self.session.post(
                self.AUTH_URL,
                data={
                    "grant_type": "client_credentials",
                    "scope": "o2dsoffre api_offresdemploiv2"
                },
                auth=(self.client_id, self.client_secret)
            )
            response.raise_for_status()

            data = response.json()
            self._access_token = data["access_token"]

            # Calculer l'expiration (avec une marge de sécurité de 60 secondes)
            expires_in = data.get("expires_in", 3600)
            self._token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)

            self.logger.info(f"Token OAuth2 obtenu, valide jusqu'à {self._token_expires_at}")
            return self._access_token

        except requests.RequestException as e:
            self.logger.error(f"Erreur lors de l'authentification OAuth2: {e}")
            raise
        except (KeyError, json.JSONDecodeError) as e:
            self.logger.error(f"Réponse d'authentification invalide: {e}")
            raise

    def _build_api_url(self) -> str:
        """
        Construit l'URL de l'API de recherche France Travail.

        Returns:
            URL complète de l'API de recherche
        """
        return f"{self.base_url}/offres/search"

    def _extract_search_params(self, search_url: str) -> Dict:
        """
        Extrait les paramètres de recherche depuis l'URL frontend France Travail.

        Args:
            search_url: URL de recherche France Travail (ex: https://candidat.francetravail.fr/...)

        Returns:
            Dictionnaire des paramètres pour l'API France Travail
        """
        parsed = urlparse(search_url)
        query_params = parse_qs(parsed.query)

        def get_first(values, default=""):
            """Retourne la première valeur d'une liste ou la valeur défaut."""
            return values[0] if values else default

        # Construire le payload selon l'API France Travail
        payload = {}

        # Mots-clés (recherche textuelle)
        mots_cles = get_first(query_params.get("motsCles", []))
        if mots_cles:
            payload["motsCles"] = mots_cles

        # Département (code INSEE à 2 chiffres)
        departement = get_first(query_params.get("departement", []))
        if departement:
            payload["departement"] = departement
        
        # Commune (code INSEE à 5 chiffres, paramètre "lieux" dans l'URL frontend)
        # ex: lieux=74282 → commune=74282 dans l'API
        commune = get_first(query_params.get("lieux", []))
        if commune:
            payload["commune"] = commune

        # Type de contrat
        types_contrat = query_params.get("typeContrat", [])
        if types_contrat:
            payload["typeContrat"] = types_contrat

        # Date de publication (publieeDepuis)
        publiee_depuis = get_first(query_params.get("publieeDepuis", []))
        if publiee_depuis:
            payload["publieeDepuis"] = publiee_depuis

        # Rayon géographique (en km) - si des coordonnées sont présentes
        distance = get_first(query_params.get("rayon", []))
        if distance:
            payload["distance"] = distance

        # paramètre d'ordering (ordre des résultats)
        sort = get_first(query_params.get("tri", []))
        if sort:
            payload["sort"] = sort

        self.logger.debug(f"Paramètres extraits: {payload}")
        return payload

    def scrape_search_results(
        self,
        search_url: str,
        max_pages: Optional[int] = None
    ) -> List[Dict]:
        """
        Scrape les résultats de recherche via l'API France Travail.

        Gestion de la pagination via le paramètre range (ex: "0-149", "150-299").
        Maximum 150 offres par appel.

        Args:
            search_url: URL de recherche frontend France Travail
            max_pages: Nombre maximum de pages à scraper (None = toutes)

        Returns:
            Liste de dictionnaires représentant les offres de base
        """
        self.logger.info(f"Scraping des offres France Travail depuis: {search_url}")

        # Extraire les paramètres de recherche
        params = self._extract_search_params(search_url)
        self.logger.info(f"Paramètres de recherche: {params}")

        # Initialiser la session si ce n'est pas déjà fait
        self._setup_session()

        # Obtenir le token OAuth2
        try:
            token = self._get_auth_token()
            self.session.headers.update({
                'Authorization': f'Bearer {token}',
                'Accept': 'application/json'
            })
        except Exception as e:
            self.logger.error(f"Impossible d'obtenir le token OAuth2: {e}")
            return []

        all_offers = []
        page = 1
        total_count = None

        while True:
            try:
                # Construire le range pour la pagination (0-149, 150-299, ...)
                start = len(all_offers)
                end = start + 149  # Max 150 par page (0-149 = 150 items)
                range_param = f"{start}-{end}"

                # Ajouter le range aux paramètres
                request_params = params.copy()
                request_params["range"] = range_param

                self.logger.info(
                    f"Récupération page {page} (range={range_param}, total_attendu={total_count})"
                )

                # Appel API GET
                api_url = self._build_api_url()
                response = self.session.get(api_url, params=request_params)

                # Gérer les codes 204 (no content) et 206 (partial)
                if response.status_code == 204:
                    self.logger.info("Aucune offre trouvée (204 No Content)")
                    break
                elif response.status_code == 206:
                    self.logger.info("Résultat partiel (206 Partial Content)")
                elif response.status_code == 200:
                    self.logger.info("Résultat complet (200 OK)")
                else:
                    response.raise_for_status()

                data = response.json()

                # Extraire le total depuis le header Content-Range si présent
                content_range = response.headers.get("Content-Range")
                if content_range:
                    # Format: "offres 0-149/1234" ou "offres */1234"
                    try:
                        total_part = content_range.split("/")[-1]
                        if total_part != "*":
                            total_count = int(total_part)
                            self.logger.info(f"Total d'offres disponibles: {total_count}")
                    except (ValueError, IndexError) as e:
                        self.logger.warning(f"Impossible de parser Content-Range: {e}")

                # Vérifier s'il y a des résultats
                if "resultats" not in data or not data["resultats"]:
                    self.logger.info("Aucun résultat trouvé pour cette page")
                    break

                # Extraire les offres de la page
                for offer in data["resultats"]:
                    try:
                        # ID unique de l'offre
                        offre_id = offer.get("id")
                        if not offre_id:
                            self.logger.warning("Offre sans id, ignorée")
                            continue

                        # Construction de l'URL canonique France Travail
                        # Format: https://candidat.francetravail.fr/offres/recherche/detail/{id}
                        url = f"https://candidat.francetravail.fr/offres/recherche/detail/{offre_id}"

                        # Extraire les champs pertinents
                        basic_offer = {
                            "title": offer.get("intitule", "").strip(),
                            "url": url,
                            "salary": offer.get("salaire"),
                            "date_posted": offer.get("dateCreation"),
                            "_type_contrat": offer.get("typeContrat"),
                            "_remote_work": offer.get("telepossible"),  # Oui/Non
                            "_id_offre": offre_id,
                            "_entreprise": offer.get("entreprise", {}).get("nom", "")
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
                if total_count is not None and len(all_offers) >= total_count:
                    self.logger.info(f"Toutes les offres collectées ({len(all_offers)}/{total_count})")
                    break

                if max_pages is not None and page >= max_pages:
                    self.logger.info(f"Limite max_pages atteinte ({max_pages} pages)")
                    break

                # Si on a reçu moins de 150 offres, c'est probablement la dernière page
                if len(data.get("resultats", [])) < 150:
                    self.logger.info(f"Dernière page atteinte (seulement {len(data['resultats'])} offres)")
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
        Scrape les détails complets d'une liste d'offres via l'API France Travail.

        Args:
            job_offers: Liste des offres avec au moins 'title' et 'url' (et '_id_offre' si disponible)

        Returns:
            Liste d'objets JobOffer avec détails complets
        """
        self.logger.info(f"Scraping des détails pour {len(job_offers)} offres")
        self._setup_session()

        detailed_offers = []

        for i, job_dict in enumerate(job_offers):
            try:
                self.logger.info(f"Traitement de l'offre {i+1}/{len(job_offers)}: {job_dict['title']}")

                # Extraire l'ID de l'offre depuis l'URL ou le dict
                offre_id = job_dict.get("_id_offre")
                if not offre_id:
                    # Tentative d'extraction depuis l'URL
                    # Format: https://candidat.francetravail.fr/offres/recherche/detail/{id}
                    url_parts = job_dict['url'].rstrip('/').split('/')
                    offre_id = url_parts[-1]

                if not offre_id:
                    self.logger.warning(f"Impossible d'extraire l'ID depuis {job_dict['url']}")
                    raise ValueError("ID d'offre manquant")

                # Appel API détail
                detail_url = f"{self.base_url}/offres/{offre_id}"
                response = self.session.get(detail_url)
                response.raise_for_status()
                data = response.json()

                # Parser les données de détail
                offer_data = data

                # Company : nom de l'entreprise
                company = offer_data.get("entreprise", {}).get("nom")
                if not company:
                    company = None

                # Location : combiner lieu et localisation
                lieu_travail = offer_data.get("lieuTravail", {})
                location = lieu_travail.get("libelle") or None

                # Description : concaténation de plusieurs champs
                description_parts = []

                # Description du poste
                formation = offer_data.get("formation", [])
                if isinstance(formation, list):
                    for form in formation:
                        if isinstance(form, dict):
                            libelle_formation = form.get("libelle")
                            if libelle_formation:
                                description_parts.append(f"Formation: {libelle_formation}")

                # Compétences
                competences = offer_data.get("competences", [])
                if isinstance(competences, list):
                    comp_names = [c.get("libelle") for c in competences if isinstance(c, dict) and c.get("libelle")]
                    if comp_names:
                        description_parts.append(f"Compétences: {', '.join(comp_names)}")

                # Salaire
                salaire_obj = offer_data.get("salaire", {})
                salaire = salaire_obj.get("libelle") if salaire_obj else None
                if salaire:
                    description_parts.append(f"Salaire: {salaire}")

                # Conditions d'exercice
                conditions = offer_data.get("conditionsExercice")
                if conditions:
                    description_parts.append(f"Conditions: {conditions}")

                # Description principale
                description_texte = offer_data.get("description")
                if description_texte:
                    description_parts.insert(0, description_texte)

                description = "\n\n---\n\n".join(description_parts) if description_parts else None

                # Mapping des types
                type_contrat_code = job_dict.get("_type_contrat")
                employment_type = self.EMPLOYMENT_TYPE_MAP.get(
                    type_contrat_code, EmploymentType.UNKNOWN
                ) if type_contrat_code else EmploymentType.UNKNOWN

                # Télétravail : depuis _remote_work (Oui/Non)
                remote_code = job_dict.get("_remote_work")
                if remote_code == "Oui":
                    # France Travail ne précise pas toujours si full/hybrid, on suppose FULL si indiqué
                    remote_work = RemoteWorkType.FULL
                elif remote_code == "Non":
                    remote_work = RemoteWorkType.NONE
                else:
                    remote_work = RemoteWorkType.UNKNOWN

                # Date de publication : format "YYYY-MM-DDTHH:MM:SS" → "DD/MM/YYYY"
                date_published = job_dict.get("date_posted")
                if date_published:
                    try:
                        # Peut être "2024-03-15T00:00:00.000" ou similaire
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
                    salary=salaire, #job_dict.get("salary") or salaire if 'salaire' in locals() else None,
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
