# Multi-Site Job Scraper

Un outil Python de veille automatisée des offres d'emploi sur **HelloWork**,
**Welcome to the Jungle** et **APEC**, conçu pour **gagner du temps dans la
recherche d'emploi** : collecter, scorer, dédupliquer, suivre et piloter ses
candidatures depuis un seul endroit.

## Objectif

La recherche d'emploi implique de consulter régulièrement les mêmes sites,
de retrouver des offres déjà vues et de perdre le fil de ses candidatures.
Ce scraper automatise la veille et centralise toutes les offres avec scoring
généré par l'IA dans une base PostgreSQL pour se concentrer sur l'essentiel :
postuler aux bonnes offres.

**Ce que ça change concrètement :**
- Lance le scraper → seules les **nouvelles offres** sont scrapées (les connues sont ignorées)
- Consulte les nouvelles offres en une commande
- Score l'offre avec l'IA
- Marque une candidature en une ligne de terminal
- Suit ses stats : offres vues, postulées, expirées

## Fonctionnalités

- **Multi-sources** : HelloWork, Welcome to the Jungle et APEC dans un seul run
- Scraping des pages de résultats avec gestion de la pagination
- Extraction des détails complets : titre, entreprise, localisation, contrat, télétravail, salaire, description, date
- **Déduplication automatique** : vérifie chaque URL en base avant de scraper les détails
- **Persistance PostgreSQL** : toutes les offres sont stockées avec leur historique
- **Scoring IA** par offre via OpenRouter API (modèle `stepfun/step-3.5-flash`) :
  - Analyse sur 5 critères pondérés (alignement compétences, potentiel de progression, probabilité d'être retenu, attractivité entreprise, faisabilité pratique)
  - Score global `/10` et recommandation (🟢🟡🟠🔴)
- **Suivi des candidatures** : marque les offres où tu as postulé (`applied`)
- **Détection des offres expirées** : passe `is_active = False` après N jours sans réapparition
- **CLI de gestion** (`manage_jobs.py`) : consulter, filtrer, marquer les offres
- Profils de recherche configurables par site et critères
- Export CSV/JSON optionnel (`--export`)
- Logging complet pour le débogage

## Architecture du projet

```
.
├── run_scraper.py              # Script principal multi-sites
├── manage_jobs.py              # CLI de gestion des offres en base
├── score_jobs.py               # Scoring IA des offres
├── config.py                   # Profils de recherche (non versionné)
├── config.example.py           # Template de configuration
├── requirements.txt
├── .env                        # Credentials PostgreSQL + OpenRouter (non versionné)
├── .env.example                # Template .env
├── scraper/
│   ├── base_scraper.py         # Classe abstraite BaseScraper (Selenium)
│   ├── base_api_scraper.py     # Classe abstraite BaseApiScraper (REST API, sans Selenium)
│   ├── hellowork_scraper.py    # Scraper HelloWork (hérite de BaseScraper)
│   ├── wttj_scraper.py         # Scraper Welcome to the Jungle (hérite de BaseScraper)
│   ├── apec_scraper.py         # Scraper APEC (hérite de BaseApiScraper)
│   ├── models/
│   │   └── job_offer.py        # Modèle de données JobOffer
│   ├── parsers/
│   │   ├── job_details_parser.py        # Parseur détails HelloWork
│   │   └── wttj_job_details_parser.py   # Parseur détails WTTJ
│   ├── database/
│   │   └── db_manager.py       # Gestion PostgreSQL
│   └── config/
│       └── settings.py         # Configuration centralisée (DB, Selenium)
├── scoring/
│   ├── ai_scorer.py            # Moteur de scoring IA
│   └── scoring_prompt.py       # Prompt de scoring personnalisé
└── data/                       # Export CSV/JSON (optionnel)
```

### Architecture extensible

Le projet repose sur **deux classes abstraites** selon la nature de la source :

| Classe de base | Technologie | Usage |
|---|---|---|
| `BaseScraper` | Selenium | Sites avec rendu JavaScript (HelloWork, WTTJ) |
| `BaseApiScraper` | requests | Sources avec API REST JSON (APEC) |

Les deux classes exposent la **même interface publique** (`scrape_search_with_details`) et s'intègrent identiquement dans le `SCRAPER_REGISTRY`.

```python
# Ajouter une source Selenium (pages JS) :
class XxxScraper(BaseScraper):
    def _get_total_pages(self, search_url): ...
    def _build_page_url(self, base_url, page): ...
    def scrape_search_results(self, search_url, max_pages=None): ...
    def scrape_job_details(self, job_offers): ...

# Ajouter une source API REST :
class YyyScraper(BaseApiScraper):
    def scrape_search_results(self, search_url, max_pages=None): ...
    def scrape_job_details(self, job_offers): ...

# Dans les deux cas, même enregistrement :
SCRAPER_REGISTRY = {
    "hellowork": HelloWorkScraper,
    "wttj": WttjScraper,
    "apec": ApecScraper,
    "xxx": XxxScraper,   # ← ajouter ici
}
```

## Prérequis

- Python 3.10+
- PostgreSQL 14+
- Google Chrome + ChromeDriver (pour HelloWork et WTTJ, gérés automatiquement par `webdriver-manager`)
- Compte [OpenRouter](https://openrouter.ai/) (accès gratuit disponible)

## Installation

```bash
# 1. Cloner le projet
git clone https://github.com/AntoinePro74/hellowork-scraper.git
cd hellowork-scraper

# 2. Créer et activer l'environnement virtuel
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Configurer les variables d'environnement
cp .env.example .env
# Renseigner : DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, OPENROUTER_API_KEY
```

## Configuration

### Base de données PostgreSQL

```bash
createdb job_scraper
cp .env.example .env
```

Éditer `.env` :
```ini
DB_HOST=localhost
DB_PORT=5432
DB_NAME=job_scraper
DB_USER=ton_username
DB_PASSWORD=

OPENROUTER_API_KEY=your_api_key
```

La table `job_offers` est créée **automatiquement** au premier lancement.

### Profils de recherche

```bash
cp config.example.py config.py
```

Éditer `config.py` — chaque profil doit spécifier le champ `"site"` :

```python
SEARCH_PROFILES = [
    # Profils HelloWork
    {
        "site": "hellowork",
        "label": "Account Manager France CDI",
        "url": "https://www.hellowork.com/fr-fr/emploi/recherche.html?k=account+manager&l=France&c=CDI"
    },
    # Profils Welcome to the Jungle
    {
        "site": "wttj",
        "label": "Account Manager WTTJ",
        "url": "https://www.welcometothejungle.com/fr/jobs?query=%22Account%20Manager%22&refinementList%5Bcontract_type%5D%5B%5D=full_time&refinementList%5Boffices.country_code%5D%5B%5D=FR&refinementList%5Bremote%5D%5B%5D=fulltime&page=1&sortBy=mostRecent"
    },
    # Profils APEC (passer l'URL de recherche frontend directement)
    {
        "site": "apec",
        "label": "Account Manager APEC CDI télétravail",
        "url": "https://www.apec.fr/candidat/recherche-emploi.html/emploi?motsCles=account+manager&typesContrat=101888&typesTeletravail=20767&sortsType=DATE"
    },
    # France Travail - Account Manager (France, CDI)
    {
        "label": "Account Manager France France Travail",
        "site": "france_travail",
        "url": "https://candidat.francetravail.fr/offres/recherche?emission=1&lieux=99100&motsCles=Account+Manager&offresPartenaires=true&range=0-19&rayon=10&tri=0&typeContrat=CDI"
    },
]
```

> **Note APEC** : l'URL est l'URL frontend telle qu'elle apparaît dans le navigateur après avoir configuré tes filtres sur apec.fr. Les paramètres `typesContrat` (ex: `101888` = CDI) et `typesTeletravail` (ex: `20767` = télétravail complet) sont extraits automatiquement par le scraper.
>
> **Note France Travail** : le scraper utilise l'API partenaire France Travail (OAuth2). Tu dois créer une application sur [francetravail.io](https://francetravail.io/) pour obtenir un `client_id` et `client_secret`. Ajoute ces identifiants dans ton `.env` :
> ```env
> FRANCE_TRAVAIL_CLIENT_ID=ton_client_id
> FRANCE_TRAVAIL_CLIENT_SECRET=ton_client_secret
> ```
> Les profils se configurent de la même façon avec `"site": "france_travail"`. Les paramètres d'URL supportés sont : `motsCles`, `departement` (code INSEE), `typeContrat` (CDI, CDD...), `publieeDepuis` (nombre de jours).

## Utilisation

### Lancer le scraper

```bash
# Scraping complet (tous les profils, toutes les sources)
python run_scraper.py

# Limiter à N pages par profil (test rapide)
python run_scraper.py --max-pages 2

# Afficher les navigateurs Selenium (debug, mode non-headless)
python run_scraper.py --visible

# Re-scraper les offres déjà connues en base
python run_scraper.py --rescrape-existing
```

> **Note** : `--visible` n'a d'effet que sur les scrapers Selenium (HelloWork, WTTJ). APEC utilise une API REST et n'ouvre aucun navigateur.

### Scorer les offres (IA)

```bash
# Toutes les offres non scorées
python score_jobs.py

# Limiter le nombre d'offres traitées
python score_jobs.py --limit 20
```

### Gérer les offres

```bash
# Voir les nouvelles offres à traiter
python manage_jobs.py list --new

# Voir toutes les offres actives
python manage_jobs.py list --active

# Voir les candidatures envoyées
python manage_jobs.py list --applied

# Marquer une candidature
python manage_jobs.py apply "https://www.apec.fr/candidat/recherche-emploi.html/emploi/detail-offre/178350363W"

# Statistiques globales
python manage_jobs.py stats

# Exporter en CSV
python manage_jobs.py export
python manage_jobs.py export --min-score 6.0 --output data/top_offres.csv
```

Exemple de sortie `stats` :
```
============================================================
JOB OFFERS STATISTICS
============================================================
| Metric                             |   Count |
|------------------------------------|---------|
| Total offers                       |     147 |
| New offers (to apply)              |      51 |
| Applied offers                     |       2 |
| Inactive offers                    |      94 |
============================================================
```

---

## 🤖 Scoring IA — Détail

Le scoring utilise un prompt personnalisé basé sur le profil du candidat.
Chaque offre est évaluée sur 5 critères pondérés :

| Critère | Pondération |
|---|---|
| Alignement compétences (must-have vs nice-to-have) | 30% |
| Potentiel de progression (objectifs 2-3 ans) | 25% |
| Probabilité d'être retenu | 25% |
| Attractivité de l'entreprise | 10% |
| Faisabilité pratique (localisation, télétravail) | 10% |

### Recommandations

| Emoji | Seuil | Signification |
|---|---|---|
| 🟢 | ≥ 8.5 | Postuler en priorité |
| 🟡 | 6.5 – 8.4 | Postuler avec adaptation |
| 🟠 | 4.5 – 6.4 | Postuler si peu d'alternatives |
| 🔴 | < 4.5 | Passer son chemin |

### Robustesse du parsing

Le parser gère les variations de format de l'IA avec 3 niveaux de fallback :
1. **Regex principal** — cherche `Score global pondéré : X/10`
2. **Fallback 1** — cherche le dernier `X/10` non parenthésé
3. **Fallback 2** — calcule la somme des pondérations `XX% × Y = Z`

---

## Schéma de la base de données

```sql
CREATE TABLE job_offers (
    id              SERIAL PRIMARY KEY,
    title           TEXT NOT NULL,
    url             TEXT UNIQUE NOT NULL,   -- clé de déduplication
    company         TEXT,
    location        TEXT,
    employment_type TEXT,
    remote_work     TEXT,
    source          TEXT,                   -- 'hellowork', 'wttj' ou 'apec'
    salary          TEXT,
    description     TEXT,
    date_posted     TEXT,
    new_offer       BOOLEAN DEFAULT TRUE,   -- nouvelle depuis le dernier run
    applied         BOOLEAN DEFAULT FALSE,  -- candidature envoyée
    is_active       BOOLEAN DEFAULT TRUE,   -- offre toujours visible
    last_seen_at    TIMESTAMP,              -- dernière apparition dans les résultats
    scraped_at      TIMESTAMP DEFAULT NOW()
);
```

## Requêtes SQL utiles

```sql
-- Nouvelles offres à traiter
SELECT title, company, location, url
FROM job_offers WHERE new_offer = TRUE AND is_active = TRUE;

-- Mes candidatures
SELECT title, company, location, scraped_at
FROM job_offers WHERE applied = TRUE;

-- Offres par source
SELECT source, COUNT(*) FROM job_offers GROUP BY source;

-- Nouvelles offres cette semaine
SELECT COUNT(*) FROM job_offers
WHERE scraped_at > NOW() - INTERVAL '7 days';
```

## Technologies

- **Selenium** : navigation automatisée sur pages JavaScript (HelloWork, WTTJ)
- **requests** : appels API REST (APEC)
- **BeautifulSoup + lxml** : parsing HTML
- **psycopg2** : connexion PostgreSQL
- **pandas** : export CSV
- **tabulate** : affichage CLI en tableaux
- **python-dotenv** : gestion des variables d'environnement
- **webdriver-manager** : gestion automatique de ChromeDriver

---

## 🔧 Personnalisation

### `scoring/scoring_prompt.py`

Personnalise le prompt avec ton profil (expérience, compétences, critères de
recherche, localisation). C'est le fichier clé à adapter à ta situation.

### `.env`

```env
DATABASE_URL=postgresql://user:password@localhost:5432/job_scraper
OPENROUTER_API_KEY=sk-or-xxxxxxxxxxxx
```

---

## 📊 Performances observées

- **Taux de scoring réussi** : ~85% (limite du modèle free OpenRouter)
- **Taux de parsing valide** : ~92% des réponses exploitables
- **Durée par offre (scoring)** : ~15-20 secondes (latence API)
- **Durée par offre APEC (détail)** : ~0.6s (0.5s sleep + réseau)
- **Corpus testé** : 147 offres multi-sources, score moyen 4.5/10

---

## 🗺️ Roadmap

- [x] Ajout scraper Welcome to the Jungle
- [x] Ajout scraper APEC (via API REST, sans Selenium)
- [x] Ajout scraper France Travail (via API REST, sans Selenium)
- [x] Automatisation via n8n avec message télégram quotidien
- [ ] Ajout scraper JobUp.ch (marché franco-suisse)
- [ ] Ajout dans n8n d'une vérification hebdo qu'il n'y a pas d'annonce vide en base
- [ ] Ajout dans n8n d'une vérification hebdo qu'il n'y a pas de scoring non exploitable
- [ ] Ajout dans n8n d'un intéraction via télégram pour avoir le Top des offres dispos
- [ ] Déduplication avancée sur `(title, company, location)`

---

## 📄 Licence

Usage personnel. Ne pas utiliser pour du scraping massif ou commercial.