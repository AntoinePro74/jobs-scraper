#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Scorer IA pour évaluer les offres d'emploi avec OpenRouter.

Utilise le modèle StepFun via OpenRouter pour analyser les offres
et fournir un score, une recommandation et une analyse détaillée.
"""

import os
import re
import time
import logging
from typing import Optional, Dict
from openai import OpenAI

logger = logging.getLogger(__name__)

# Configuration OpenRouter
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "stepfun/step-3.5-flash:free"


def _load_scoring_prompt() -> str:
    """
    Charge le prompt de scoring depuis scoring_prompt.py (fichier personnel).
    Si le fichier n'existe pas, utilise scoring_prompt.example.py et log un warning.

    Returns:
        str: Le template de prompt
    """
    # Essayer d'abord le fichier personnel
    personal_prompt_path = "scoring_prompt.py"
    example_prompt_path = "scoring_prompt.example.py"

    try:
        if os.path.exists(personal_prompt_path):
            with open(personal_prompt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.info(f"Prompt de scoring chargé depuis {personal_prompt_path}")
            return content
        else:
            logger.warning(
                f"Fichier {personal_prompt_path} non trouvé. "
                f"Utilisation de l'exemple {example_prompt_path}. "
                f"Créez votre propre fichier {personal_prompt_path} pour personnaliser le prompt."
            )
            with open(example_prompt_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return content
    except FileNotFoundError as e:
        logger.error(f"Impossible de charger le prompt : {e}")
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la lecture du prompt : {e}")
        raise


def _format_job_offer_for_prompt(job: Dict) -> str:
    """
    Construit le texte de l'offre à injecter dans le prompt.

    Args:
        job: Dictionnaire contenant les champs de l'offre

    Returns:
        str: Description formatée de l'offre
    """
    parts = []

    # Titre et entreprise
    parts.append(f"**Titre**: {job.get('title', 'N/A')}")
    parts.append(f"**Entreprise**: {job.get('company', 'N/A')}")
    parts.append(f"**Localisation**: {job.get('location', 'N/A')}")

    # Type de contrat et télétravail
    employment_type = job.get('employment_type', 'N/A')
    remote_work = job.get('remote_work', 'N/A')
    parts.append(f"**Type de contrat**: {employment_type}")
    parts.append(f"**Télétravail**: {remote_work}")

    # Salaire
    salary = job.get('salary')
    if salary:
        parts.append(f"**Salaire**: {salary}")

    # Description (champ le plus important)
    description = job.get('description', 'Aucune description fournie')
    parts.append(f"\n**Description complète**:\n{description}")

    return "\n".join(parts)


def _parse_ai_response(response_text: str) -> Optional[Dict[str, any]]:
    """
    Parse la réponse de l'IA pour extraire le score, la recommandation et l'analyse.

    Args:
        response_text: Texte brut de la réponse de l'IA

    Returns:
        Dict contenant ai_score (float), ai_recommendation (str), ai_analysis (str)
        ou None si le parsing échoue
    """
    try:
        # Extraction du score global avec regex permissive
        # Gère : **Score global**, espaces optionnels, score entier ou décimal, astérisques
        score_pattern = r'\*{0,2}[Ss]core\s+[Gg]lobal(?:\s+[Pp]ondéré)?\s*\*{0,2}\s*:\s*\*{0,2}\s*(\d+(?:[.,]\d+)?)\s*\*{0,2}\s*/\s*10'
        score_match = re.search(score_pattern, response_text)

        if not score_match:
            # Fallback 1 : chercher le dernier score non entre parenthèses (type X/10)
            fallback_matches = re.findall(
                r'(?<!\()\b(\d+(?:[.,]\d+)?)\s*/\s*10\b(?!\))',
                response_text
            )
            if fallback_matches:
                score_str = fallback_matches[-1].replace(',', '.')
                ai_score = float(score_str)
                logger.warning(f"Score extrait via fallback regex : {ai_score}")
            else:
                # Fallback 2 : calculer la somme des notes pondérées si le détail est présent
                weighted_matches = re.findall(
                    r'\d+%\s*[×x]\s*\d+(?:[.,]\d+)?\s*=\s*(\d+(?:[.,]\d+)?)',
                    response_text
                )
                if weighted_matches and len(weighted_matches) >= 3:
                    try:
                        total = sum(float(v.replace(',', '.')) for v in weighted_matches)
                        if 0 < total <= 10:
                            ai_score = round(total, 2)
                            logger.warning(f"Score calculé via somme pondérée : {ai_score}")
                        else:
                            logger.warning("Impossible d'extraire le score global de la réponse")
                            logger.warning(f"Réponse brute (fin, 600 chars) : {response_text[-600:]}")
                            return None
                    except Exception as e:
                        logger.warning(f"Erreur lors du calcul des pondérations : {e}")
                        logger.warning(f"Réponse brute (fin, 600 chars) : {response_text[-600:]}")
                        return None
                else:
                    logger.warning("Impossible d'extraire le score global de la réponse")
                    logger.warning(f"Réponse brute (fin, 600 chars) : {response_text[-600:]}")
                    return None
        else:
            score_str = score_match.group(1).replace(',', '.')
            ai_score = float(score_str)

        # Extraction de la recommandation (ligne commençant par un emoji)
        # Pattern permissif : gère espaces et astérisques autour de l'emoji
        recommendation_pattern = r'\*{0,2}\s*([🟢🟡🟠🔴][^\n]*?)\s*\*{0,2}(?:\n|$)'
        rec_match = re.search(recommendation_pattern, response_text)

        ai_recommendation = None

        if rec_match:
            ai_recommendation = rec_match.group(1).strip()
        else:
            logger.warning("Impossible d'extraire la recommandation de la réponse")
            # Fallback 1 : première ligne commençant par un emoji
            lines = response_text.split('\n')
            for line in lines:
                if any(emoji in line for emoji in ['🟢', '🟡', '🟠', '🔴']):
                    ai_recommendation = line.strip()
                    break

            # Fallback 2 : cherche l'emoji n'importe où dans la réponse
            if not ai_recommendation:
                for emoji in ['🟢', '🟡', '🟠', '🔴']:
                    if emoji in response_text:
                        for line in response_text.split('\n'):
                            if emoji in line:
                                ai_recommendation = line.strip().lstrip('*').strip()
                                break
                        if ai_recommendation:
                            break

        if not ai_recommendation:
            ai_recommendation = "Non déterminée"

        # L'analyse complète est la réponse brute
        ai_analysis = response_text.strip()

        return {
            "ai_score": ai_score,
            "ai_recommendation": ai_recommendation,
            "ai_analysis": ai_analysis
        }

    except Exception as e:
        logger.error(f"Erreur lors du parsing de la réponse IA : {e}")
        # Log de la réponse brute pour diagnostic (fin de la réponse)
        if 'response_text' in locals():
            logger.warning(f"Réponse brute (fin, 600 chars) : {response_text[-600:]}")
        return None


def score_job_offer(job: Dict) -> Optional[Dict[str, any]]:
    """
    Score une offre d'emploi via l'API OpenRouter.

    Args:
        job: Dictionnaire contenant les champs de l'offre
            (title, company, location, employment_type, remote_work, salary, description)

    Returns:
        Dict avec ai_score (float), ai_recommendation (str), ai_analysis (str)
        ou None en cas d'échec
    """
    # Charger le prompt
    try:
        prompt_template = _load_scoring_prompt()
    except Exception as e:
        logger.error(f"Impossible de charger le prompt : {e}")
        return None

    # Formater l'offre
    job_offer_text = _format_job_offer_for_prompt(job)
    prompt = prompt_template.format(job_offer=job_offer_text)

    # Configurer le client OpenAI pour OpenRouter
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        logger.error("OPENROUTER_API_KEY non définie dans l'environnement")
        return None

    client = OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=api_key,
    )

    # Appel avec retry
    max_retries = 3  # 2 retries + 1 essai initial
    for attempt in range(max_retries):
        try:
            logger.debug(f"Appel OpenRouter (tentative {attempt + 1}/{max_retries})")

            response = client.chat.completions.create(
                model=OPENROUTER_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=2000,
                temperature=0.7
            )

            content = response.choices[0].message.content
            if not content or content.strip() == "":
                logger.warning("Réponse vide reçue de l'API (content=None ou vide)")
                return None  # déclenchera le retry existant
            response_text = content.strip()

            # Parser la réponse
            result = _parse_ai_response(response_text)
            if result:
                logger.info(f"Offre scorée : score={result['ai_score']}, reco={result['ai_recommendation'][:30]}...")
                return result
            else:
                logger.warning("Réponse reçue mais impossible à parser")
                return None

        except Exception as e:
            error_msg = str(e)
            logger.warning(f"Erreur OpenRouter (tentative {attempt + 1}/{max_retries}) : {error_msg}")

            # Gestion des retry selon le code d'erreur
            if "429" in error_msg or "rate limit" in error_msg.lower():
                if attempt < max_retries - 1:
                    sleep_time = 5 * (attempt + 1)
                    logger.info(f"Rate limit détecté, pause de {sleep_time}s avant retry...")
                    time.sleep(sleep_time)
                    continue
            elif "500" in error_msg or "503" in error_msg:
                if attempt < max_retries - 1:
                    sleep_time = 2
                    logger.info(f"Erreur serveur {error_msg}, pause de {sleep_time}s avant retry...")
                    time.sleep(sleep_time)
                    continue

            if attempt == max_retries - 1:
                logger.error(f"Échec définitif après {max_retries} tentatives : {error_msg}")
                return None

    return None


def score_pending_jobs(db_manager, limit: int = 20) -> int:
    """
    Score les offres en attente (ai_score IS NULL) dans la base de données.

    Args:
        db_manager: Instance de DatabaseManager
        limit: Nombre maximum d'offres à scorer (default: 20)

    Returns:
        int: Nombre d'offres scorées avec succès
    """
    logger.info(f"Récupération de jusqu'à {limit} offres à scorer...")

    try:
        # Récupérer les offres à scorer
        query = """
            SELECT title, url, company, location, employment_type, remote_work,
                   salary, description, date_posted
            FROM job_offers
            WHERE ai_score IS NULL AND is_active = TRUE
            LIMIT %s;
        """
        db_manager.cursor.execute(query, (limit,))
        rows = db_manager.cursor.fetchall()

        if not rows:
            logger.info("Aucune offre à scorer.")
            return 0

        logger.info(f"{len(rows)} offres à scorer")

        # Convertir en dictionnaires
        jobs_to_score = []
        for row in rows:
            job_dict = {
                'title': row[0],
                'url': row[1],
                'company': row[2],
                'location': row[3],
                'employment_type': row[4],
                'remote_work': row[5],
                'salary': row[6],
                'description': row[7],
                'date_posted': row[8],
            }
            jobs_to_score.append(job_dict)

        # Scorer chaque offre
        scored_count = 0
        for idx, job in enumerate(jobs_to_score, 1):
            logger.info(f"[{idx}/{len(jobs_to_score)}] Scoring : {job['title'][:50]}...")

            result = score_job_offer(job)

            if result:
                # Mettre à jour la base de données
                try:
                    update_query = """
                        UPDATE job_offers
                        SET ai_score = %s,
                            ai_recommendation = %s,
                            ai_analysis = %s,
                            scored_at = NOW()
                        WHERE url = %s;
                    """
                    db_manager.cursor.execute(
                        update_query,
                        (
                            result['ai_score'],
                            result['ai_recommendation'],
                            result['ai_analysis'],
                            job['url']
                        )
                    )
                    db_manager.conn.commit()
                    scored_count += 1
                    logger.info(f"  ✓ Score enregistré : {result['ai_score']}/10")
                except Exception as e:
                    logger.error(f"  ✗ Erreur lors de la mise à jour DB : {e}")
                    db_manager.conn.rollback()
            else:
                logger.warning(f"  ✗ Échec du scoring pour cette offre")

            # Pause pour respecter rate limit (modèle gratuit)
            if idx < len(jobs_to_score):
                logger.debug("Pause de 2s avant la prochaine offre...")
                time.sleep(2)

        logger.info(f"Scoring terminé : {scored_count}/{len(jobs_to_score)} offres scorées avec succès")
        return scored_count

    except Exception as e:
        logger.error(f"Erreur lors du scoring des offres : {e}")
        return 0
