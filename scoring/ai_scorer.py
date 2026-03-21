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
from typing import Optional, Dict, Any
from openai import OpenAI
from scoring_prompt import SCORING_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)

# Configuration OpenRouter
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = "stepfun/step-3.5-flash:free"



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
        score_pattern = (
            r'\*{0,2}[Ss]core'           # "Score" avec astérisques optionnels
            r'(?:\s+[Gg]lobal)?'         # "global" optionnel
            r'(?:\s+[Pp]ondéré)?'        # "pondéré" optionnel
            r'\s*\*{0,2}'                # astérisques fermants optionnels
            r'\s*[:=]\s*'                # séparateur : ou =
            r'\*{0,2}\s*'                # astérisques avant le chiffre
            r'(\d+(?:[.,]\d+)?)'         # le score (entier ou décimal, . ou ,)
            r'\s*\*{0,2}'                # astérisques après le chiffre
            r'\s*/\s*10'                 # /10
        )
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
                            logger.warning(f"Réponse brute (début, 200 chars) : {response_text[:200]}")
                            logger.warning(f"Réponse brute (fin, 600 chars) : {response_text[-600:]}")
                            return None
                    except Exception as e:
                        logger.warning(f"Erreur lors du calcul des pondérations : {e}")
                        logger.warning(f"Réponse brute (début, 200 chars) : {response_text[:200]}")
                        logger.warning(f"Réponse brute (fin, 600 chars) : {response_text[-600:]}")
                        return None
                else:
                    logger.warning("Impossible d'extraire le score global de la réponse")
                    logger.warning(f"Réponse brute (début, 200 chars) : {response_text[:200]}")
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
        # Log de la réponse brute pour diagnostic (début et fin)
        if 'response_text' in locals():
            logger.warning(f"Réponse brute (début, 200 chars) : {response_text[:200]}")
            logger.warning(f"Réponse brute (fin, 600 chars) : {response_text[-600:]}")
        return None


def score_job_offer(job: Dict) -> Optional[Dict[str, Any]]:
    """
    Score une offre d'emploi via l'API OpenRouter.

    Args:
        job: Dictionnaire contenant les champs de l'offre
            (title, company, location, employment_type, remote_work, salary, source, date_posted, description)

    Returns:
        Dict avec ai_score (float), ai_recommendation (str), ai_analysis (str)
        ou None en cas d'échec
    """
    def _safe(value: Any, default: str = "Non renseigné") -> str:
        """Retourne la valeur ou le défaut si None/vide."""
        if value is None or str(value).strip() == "":
            return default
        return str(value).strip()

    # Formater le prompt avec injection directe des champs
    # Tronquer la description si nécessaire pour respecter les limites de tokens
    description_value = _safe(job.get('description'),
                              default="Aucune description fournie")
    if len(description_value) > 5500:
        logger.debug(
            f"Description tronquée : {len(description_value)} chars → 5500"
        )
        description_value = description_value[:5500] + \
                            "\n[...description tronquée pour limite tokens...]"

    prompt = SCORING_PROMPT_TEMPLATE.format(
        title=_safe(job.get('title')),
        company=_safe(job.get('company')),
        location=_safe(job.get('location')),
        employment_type=_safe(job.get('employment_type')),
        remote_work=_safe(job.get('remote_work')),
        salary=_safe(job.get('salary')),
        source=_safe(job.get('source')),
        date_posted=_safe(job.get('date_posted')),
        description=description_value,
    )

    logger.debug(f"Prompt généré (longueur: {len(prompt)} chars)")

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
                max_tokens=6000,
                temperature=0.7
            )

            content = response.choices[0].message.content
            if not content or content.strip() == "":
                logger.warning(
                    f"Réponse vide reçue de l'API (tentative {attempt + 1}/{max_retries})"
                )
                if attempt < max_retries - 1:
                    sleep_time = 10 * (attempt + 1)
                    logger.info(f"Pause de {sleep_time}s avant retry...")
                    time.sleep(sleep_time)
                    continue
                else:
                    logger.error("Réponse vide après tous les retries")
                    return None
            response_text = content.strip()

            # Parser la réponse
            result = _parse_ai_response(response_text)
            if result:
                logger.info(f"Offre scorée : score={result['ai_score']}, reco={result['ai_recommendation'][:30]}...")
                return result
            else:
                logger.debug(f"Réponse complète ({len(response_text)} chars) : {response_text}")
                logger.warning("Réponse reçue mais impossible à parser")
                return None

        except Exception as e:
            error_msg = str(e)
            logger.warning(f"Erreur OpenRouter (tentative {attempt + 1}/{max_retries}) : {error_msg}")

            # Gestion des retry selon le code d'erreur
            if "429" in error_msg or "rate limit" in error_msg.lower():
                if attempt < max_retries - 1:
                    sleep_time = 10 * (attempt + 1)
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
                   salary, description, date_posted, source
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
                'source': row[9],
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
