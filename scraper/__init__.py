"""
Package pour le scraping du site HelloWork.

Structure du package :
├── __init__.py                 # Initialisation du package
├── hellowork_scraper.py        # Classe principale du scraper
├── models/                     # Modèles de données
│   ├── __init__.py
│   └── job_offer.py           # Modèle pour les offres d'emploi
├── parsers/                    # Parseurs pour différents types de pages
│   ├── __init__.py
│   └── job_details_parser.py  # Parseur pour les détails des offres
├── utils/                      # Fonctions utilitaires
│   ├── __init__.py
│   └── helpers.py             # Fonctions d'aide générales
└── config/                     # Configuration
    ├── __init__.py
    └── settings.py            # Paramètres de configuration
"""