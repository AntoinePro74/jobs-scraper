# HelloWork Job Scraper

Un outil Python de veille automatisée des offres d'emploi sur [HelloWork](https://www.hellowork.com/), 
conçu pour **gagner du temps dans la recherche d'emploi** : collecter, scorer, dédupliquer, 
suivre et piloter ses candidatures depuis un seul endroit.

## Objectif

La recherche d'emploi implique de consulter régulièrement les mêmes sites, 
de retrouver des offres déjà vues et de perdre le fil de ses candidatures. 
Ce scraper automatise la veille et centralise toutes les offres avec scoring généré par l'ia dans une base 
PostgreSQL pour se concentrer sur l'essentiel : postuler aux bonnes offres.

**Ce que ça change concrètement :**
- Lance le scraper → seules les **nouvelles offres** sont scrapées (les connues sont ignorées)
- Consulte les nouvelles offres en une commande
- Score l'offre avec l'ia
- Marque une candidature en une ligne de terminal
- Suit ses stats : offres vues, postulées, expirées

## Fonctionnalités

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
├── run_scraper.py              # Script principal de scraping
├── manage_jobs.py              # CLI de gestion des offres en base
├── config.py                   # Profils de recherche (non versionné)
├── config.example.py           # Template de configuration
├── requirements.txt
├── .env                        # Credentials PostgreSQL (non versionné)
├── .env.example                # Template .env
├── scraper/
│   ├── hellowork_scraper.py    # Scraper HelloWork (Selenium)
│   ├── models/
│   │   └── job_offer.py        # Modèle de données JobOffer
│   ├── parsers/
│   │   └── job_details_parser.py
│   ├── database/
│   │   └── db_manager.py       # Gestion PostgreSQL
│   └── config/
│       └── settings.py         # Configuration centralisée (DB, Selenium)
├── scoring/
│   ├── ai_scorer.py            # Moteur de scoring IA
│   └── scoring_prompt.py       # Prompt de scoring personnalisé
└── data/                       # Export CSV/JSON (optionnel)
```

## Prérequis

- Python 3.10+
- PostgreSQL 14+
- Google Chrome + ChromeDriver (compatibles)
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
# Renseigner : DATABASE_URL, OPENROUTER_API_KEY
```

## Configuration

### Base de données PostgreSQL

```bash
# Créer la base de données
createdb job_scraper

# Copier et remplir le fichier .env
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

Éditer `config.py` :
```python
SEARCH_PROFILES = [
    {
        "label": "Account Manager France CDI",
        "site": "hellowork",
        "url": "https://www.hellowork.com/fr-fr/emploi/recherche.html?k=account+manager&l=France&c=CDI"
    },
    {
        "label": "Data Analyst Rhône-Alpes",
        "site": "hellowork",
        "url": "https://www.hellowork.com/fr-fr/emploi/recherche.html?k=data+analyst&l=Rhône-Alpes"
    },
]
```

## Utilisation

### Lancer le scraper

```bash
# Scraping complet (tous les profils)
python run_scraper.py

# Limiter à N pages par profil (test rapide)
python run_scraper.py --max-pages 2

# Avec export CSV/JSON en plus
python run_scraper.py --export
```

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
python manage_jobs.py apply "https://www.hellowork.com/fr-fr/emplois/..."

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
| Total offers                       |     104 |
| New offers (to apply)              |       3 |
| Applied offers                     |       2 |
| Inactive offers                    |     101 |
============================================================
```

---

## 🤖 Scoring IA — Détail

Le scoring utilise un prompt personnalisé basé sur le profil du candidat. Chaque offre est évaluée sur 5 critères pondérés :

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
    source          TEXT DEFAULT 'hellowork',
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

- **Selenium** : navigation automatisée sur pages JavaScript
- **BeautifulSoup + lxml** : parsing HTML
- **psycopg2** : connexion PostgreSQL
- **pandas** : export CSV
- **tabulate** : affichage CLI en tableaux
- **python-dotenv** : gestion des variables d'environnement
- **webdriver-manager** : gestion automatique de ChromeDriver

---

## 🔧 Configuration

### `.env`

```env
DATABASE_URL=postgresql://user:password@localhost:5432/job_scraper
OPENROUTER_API_KEY=sk-or-xxxxxxxxxxxx
```

### `scoring/scoring_prompt.py`

Personnalise le prompt avec ton profil (expérience, compétences, critères de recherche, localisation). C'est le fichier clé à adapter à ta situation.

---

## 📊 Performances observées

- **Taux de scoring réussi** : ~85% (limite du modèle free OpenRouter)
- **Taux de parsing valide** : ~92% des réponses exploitables
- **Durée par offre** : ~15-20 secondes (latence API)
- **Corpus testé** : 112 offres, score moyen 4.5/10

---

## 🗺️ Roadmap

- [ ] Ajout scraper WelcomeToTheJungle
- [ ] Ajout scraper JobUp.ch (marché franco-suisse)
- [ ] Dashboard de visualisation (Metabase / Power BI)
- [ ] Déduplication avancée sur `(title, company, location)`
- [ ] Planification automatique (cron / launchd)

---

## 📄 Licence

Usage personnel. Ne pas utiliser pour du scraping massif ou commercial.
