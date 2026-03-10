# HelloWork Scraper

Un scraper Python pour récupérer les offres d'emploi depuis le site [HelloWork](https://www.hellowork.com/).

## Fonctionnalités

- Scraping des pages de recherche avec gestion de la pagination
- Extraction des détails complets de chaque offre (titre, entreprise, localisation, contrat, télétravail, salaire, description, date)
- Export des données en CSV et JSON
- Configuration personnalisable des URLs de recherche
- Logging complet pour le débogage

## Installation

### Prérequis

- Python 3.8+
- Chrome (pour Selenium)

### Installation des dépendances

```bash
pip install -r requirements.txt
```

## Configuration

Créez un fichier `config.py` à la racine du projet avec vos URLs de recherche :

```python
SEARCH_URLS = [
    "https://www.hellowork.com/fr-fr/emploi/recherche.html?k=account+manager&...",
    # Ajoutez vos URLs personnalisées
]
```

Ce fichier n'est pas versionné (présent dans `.gitignore`), vous pouvez le personnaliser selon vos besoins.

## Utilisation

### Commandes de base

```bash
# Exécuter le scraper avec les URLs configurées
python run_scraper.py

# Limiter le nombre de pages scrapées par URL
python run_scraper.py --max-pages 5

# Spécifier des URLs directement en ligne de commande
python run_scraper.py --urls "https://..." "https://..."
```

### Fichiers générés

Les données sont exportées dans le dossier `data/` avec un timestamp :
- `job_offers_YYYYMMDD_HHMMSS.csv`
- `job_offers_YYYYMMDD_HHMMSS.json`

## Architecture du projet

```
.
├── main.py                     # Point d'entrée simple
├── run_scraper.py              # Script principal avec export CSV/JSON
├── config.py                   # Configuration des URLs (non versionné)
├── requirements.txt            # Dépendances
├── scraper/
│   ├── hellowork_scraper.py    # Classe principale du scraper
│   ├── models/
│   │   └── job_offer.py        # Modèle de données JobOffer
│   ├── parsers/
│   │   └── job_details_parser.py  # Parseur des détails d'offre
│   └── config/
│       └── settings.py         # Paramètres de configuration
└── data/                       # Dossier de sortie (généré)
```

## Modèle de données

Chaque offre (`JobOffer`) contient :
- `title` : Titre du poste
- `url` : Lien vers l'offre
- `company` : Nom de l'entreprise
- `location` : Localisation
- `employment_type` : Type de contrat (CDI, CDD, Intérim, Freelance, Stage, Alternance)
- `remote_work` : Type de télétravail
- `salary` : Salaire (si disponible)
- `description` : Description complète
- `date_posted` : Date de publication

## Technologies

- **Selenium** : Automatisation du navigateur pour les pages JavaScript
- **BeautifulSoup + lxml** : Parsing HTML
- **pandas** : Export CSV
- **webdriver-manager** : Gestion automatique de ChromeDriver

## Licence

MIT
