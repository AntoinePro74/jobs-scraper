"""
Modèle de données pour les offres d'emploi HelloWork.
"""

from dataclasses import dataclass
from typing import Optional
from enum import Enum


class EmploymentType(Enum):
    """Types de contrat disponibles."""
    CDI = "CDI"
    CDD = "CDD"
    INTERIM = "Intérim"
    FREELANCE = "Freelance"
    STAGE = "Stage"
    ALTERNANCE = "Alternance"
    UNKNOWN = "Non spécifié"


class RemoteWorkType(Enum):
    """Types de télétravail disponibles."""
    FULL = "Télétravail complet"
    HYBRID = "Hybride"
    PARTIAL = "Partiel"
    OCCASIONAL = "Occasionnel"
    NONE = "Pas de télétravail"
    UNKNOWN = "Non spécifié"


@dataclass
class JobOffer:
    """
    Modèle représentant une offre d'emploi HelloWork.

    Attributes:
        title (str): Titre de l'offre
        url (str): URL de l'offre
        employment_type (EmploymentType): Type de contrat
        remote_work (RemoteWorkType): Type de télétravail
        salary (Optional[str]): Salaire proposé
        description (Optional[str]): Description complète de l'offre
        company (Optional[str]): Nom de l'entreprise
        location (Optional[str]): Lieu de travail
        date_posted (Optional[str]): Date de publication au format JJ/MM/AAAA
    """

    title: str
    url: str
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    remote_work: RemoteWorkType = RemoteWorkType.UNKNOWN
    salary: Optional[str] = None
    description: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    date_posted: Optional[str] = None

    def to_dict(self) -> dict:
        """
        Convertit l'objet en dictionnaire.

        Returns:
            dict: Représentation sous forme de dictionnaire
        """
        return {
            "title": self.title,
            "url": self.url,
            "employment_type": self.employment_type.value,
            "remote_work": self.remote_work.value,
            "salary": self.salary,
            "description": self.description,
            "company": self.company,
            "location": self.location,
            "date_posted": self.date_posted
        }
