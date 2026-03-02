"""
Module LLM pour le chatbot Telegram — interprétation d'intention et contexte RACI.
Fallback vers règles si LLM indisponible ou erreur.
"""
import json
import logging
from typing import Optional

log = logging.getLogger("chatbot_llm")

INTENT_PIPELINE = "pipeline"
INTENT_PIPELINE_ALL = "pipeline_all"
INTENT_AGENTS = "agents"
INTENT_RACI = "raci"
INTENT_HELP = "help"
INTENT_UNKNOWN = "unknown"


def _get_raci_context(base_json: dict) -> str:
    """Extrait le contexte RACI depuis base_json (organisation SquidResearch)."""
    try:
        for exp in base_json.get("experiences", []):
            org = (exp.get("realisation") or {}).get("organisation") or {}
            raci = org.get("raci") or {}
            if raci:
                parts = [f"RACI — {org.get('methodologie', 'Matrice RACI')}\n"]
                for role, data in raci.items():
                    if isinstance(data, dict):
                        desc = data.get("description") or data.get("responsabilite") or ""
                        statut = data.get("statut", "")
                        raci_role = data.get("raci_role", "")
                        activites = data.get("activites", [])
                        strategies = data.get("strategies_consequences", "")
                        line = f"• {role}: {statut or desc}"
                        if raci_role:
                            line += f" [{raci_role}]"
                        line += "\n"
                        if desc and not statut:
                            line += f"  {desc}\n"
                        if activites:
                            line += "  Activités: " + ", ".join(activites[:3]) + "\n"
                        if strategies:
                            line += f"  Stratégies: {strategies[:150]}...\n"
                        parts.append(line)
                return "\n".join(parts) if len(parts) > 1 else ""
    except Exception as e:
        log.warning("get_raci_context: %s", e)
    return ""


def parse_intent_llm(text: str, base_json: Optional[dict] = None) -> Optional[dict]:
    """
    Interprète l'intention via LLM. Retourne dict ou None (si erreur).
    Format retour: {
        "intent": "pipeline"|"pipeline_all"|"agents"|"raci"|"help"|"unknown",
        "url": "https://...",
        "create_draft": bool,
        "response": "..."  # pour intent raci/agents, réponse générée
    }
    """
    if not text or not text.strip():
        return None
    try:
        from core.llm_client import OpenAIClient
        client = OpenAIClient()
        if not getattr(client, "client", None):
            return None

        raci_ctx = _get_raci_context(base_json or {})
        urls_instruction = (
            "Extrais toute URL http(s) présente dans le message. Une seule URL par offre."
        )

        prompt = f"""Message utilisateur: "{text[:800]}"

Détermine l'intention et extrais les données. Réponds en JSON uniquement, sans markdown.
Intents possibles:
- pipeline: lancer candidature sur une offre (URL fournie)
- pipeline_all: candidater sur toutes les offres du dernier scan
- agents: liste des agents du système (Scraper, Matching, Generator, Drafter)
- raci: qui fait quoi, RACI, chef de projet, expert automatisation, devops, pentester
- help: aide générale, commandes
- unknown: aucune intention reconnue

{urls_instruction}

Format de réponse (JSON strict):
{{"intent": "...", "url": "..." ou "", "create_draft": true/false}}
Si intent=raci ou agents et qu'on te donne du contexte RACI, ajoute "response" avec une réponse courte et structurée.

Contexte RACI (pour intent raci/agents):
{raci_ctx[:1200] if raci_ctx else "Non disponible"}
"""

        res = client.chat_completion(
            prompt,
            system_prompt="Tu es un assistant qui analyse les messages et retourne UNIQUEMENT un objet JSON valide.",
            json_mode=True,
        )
        if not res or not isinstance(res, dict):
            return None
        intent = (res.get("intent") or "unknown").strip().lower()
        url = (res.get("url") or "").strip()
        create_draft = bool(res.get("create_draft"))
        response = (res.get("response") or "").strip()

        # Normaliser l'intent
        if "pipeline" in intent and "all" in intent:
            intent = INTENT_PIPELINE_ALL
        elif "pipeline" in intent or "candidat" in intent:
            intent = INTENT_PIPELINE
        elif "agent" in intent or "raci" in intent or "chef" in intent or "qui fait" in intent:
            intent = INTENT_RACI if "raci" in intent or "chef" in intent or "qui fait" in intent else INTENT_AGENTS
        elif "aide" in intent or "help" in intent:
            intent = INTENT_HELP

        # L'URL sera complétée par _extract_urls côté bot si vide
        return {
            "intent": intent,
            "url": url or None,
            "create_draft": create_draft,
            "response": response,
        }
    except Exception as e:
        log.warning("parse_intent_llm: %s", e)
        return None
