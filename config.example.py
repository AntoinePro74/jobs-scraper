"""
Configuration des URLs de recherche pour tous les sites.
Copiez ce fichier vers config.py et personnalisez les URLs selon vos besoins.
"""

# URLs de recherches
# Modifiez les paramètres de recherche selon vos critères
# Champ "site" : "hellowork" ou "wttj"
SEARCH_PROFILES = [
    # Exemples HelloWork
    {
        "site": "hellowork",
        "label": "Développeur Python France CDI",
        "url": "https://www.hellowork.com/..."
    },

    # Profils Welcome To The Jungle
    {
        "site": "wttj",
        "label": "Account Manager WTTJ",
        "url": "https://www.welcometothejungle.com/fr/jobs?query=%22Account%20Manager%22&refinementList%5Bcontract_type%5D%5B%5D=full_time&refinementList%5Boffices.country_code%5D%5B%5D=FR&refinementList%5Bremote%5D%5B%5D=fulltime&page=1&sortBy=mostRecent&aroundQuery=France&collections%5B%5D=remote_friendly"
    },

    # Profil APEC
    {
        "site": "apec",
        "label": "Account Manager APEC CDI télétravail",
        "url": "https://www.apec.fr/candidat/recherche-emploi.html/emploi?motsCles=account+manager&typesContrat=101888&typesTeletravail=20767&sortsType=DATE"
    },
    # Profil France Travail 
    {
        "label": "Account Manager France France Travail",
        "site": "france_travail",
        "url": "https://candidat.francetravail.fr/offres/recherche?emission=1&lieux=99100&motsCles=Account+Manager&offresPartenaires=true&range=0-19&rayon=10&tri=0&typeContrat=CDI"
    },
]
