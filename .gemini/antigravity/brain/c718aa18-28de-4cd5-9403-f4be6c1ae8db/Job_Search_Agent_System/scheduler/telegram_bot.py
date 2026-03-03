"""
Telegram Bot — Interface de controle du Job Search Agent System
Securite : whitelist user_id, rate limiting, audit log
Evite blocage : I/O bloquant exécuté en thread pour garder l'event loop réactif.
"""
import asyncio
import json
import logging
import os
import re
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.parse import urlparse
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Config
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("token")
ALLOWED_USER_IDS = set(
    int(x) for x in (os.getenv("TELEGRAM_ALLOWED_IDS") or os.getenv("TELEGRAM_USER_ID") or "").split(",") if x.strip()
)
DB_PATH = os.getenv("DB_PATH") or str(PROJECT_ROOT / "storage" / "applications.db")
LOG_PATH = os.getenv("LOG_PATH") or str(PROJECT_ROOT / "logs" / "cron.log")
FOLLOWUP_LOG = os.getenv("FOLLOWUP_LOG") or str(PROJECT_ROOT / "logs" / "followup.log")
RESOURCES_DIR = PROJECT_ROOT / "resources"
STORAGE_DIR = PROJECT_ROOT / "storage"

RATE_LIMIT = 10
RATE_WINDOW = 60
_rate_counters = defaultdict(list)

LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / "telegram_bot.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("telegram_bot")


def is_allowed(user_id: int) -> bool:
    return user_id in ALLOWED_USER_IDS


def is_authorized(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False
    if not is_allowed(user.id):
        log.warning("[BLOCKED] Unauthorized access attempt: user_id=%s", user.id)
        return False
    return True


def rate_limited(user_id: int) -> bool:
    now = datetime.now()
    window_start = now - timedelta(seconds=RATE_WINDOW)
    _rate_counters[user_id] = [t for t in _rate_counters[user_id] if t > window_start]
    if len(_rate_counters[user_id]) >= RATE_LIMIT:
        return True
    _rate_counters[user_id].append(now)
    return False


def guard(func):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not is_authorized(update):
            return  # Blocage silencieux
        if rate_limited(update.effective_user.id):
            await update.message.reply_text("Rate limit atteint.")
            return
        log.info("CMD %s — user=%s", func.__name__, update.effective_user.id)
        await func(update, ctx)

    wrapper.__name__ = func.__name__
    return wrapper


def tail_log(path: str, n: int = 25) -> str:
    """Dernières N lignes d'un fichier (cross-platform, sans subprocess tail)."""
    path_obj = Path(path)
    if not path_obj.exists():
        return "(fichier absent)"
    try:
        with path_obj.open(encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-n:]) if lines else "(vide)"
    except Exception as e:
        log.warning("tail_log %s: %s", path[:50], e)
        return "(erreur lecture)"


def _load_base_json() -> dict:
    """Charge le profil candidat (base_real, cv_base, base.json)."""
    for name in ("base_real.json", "cv_base_datas_pour_candidatures.json", "base.json"):
        path = RESOURCES_DIR / name
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    raise FileNotFoundError("Aucun profil dans resources/ (base_real.json, base.json)")


def _run_pipeline_sync(job_url: str, create_draft: bool) -> tuple:
    """
    Lance l'orchestrateur (extraction, matching, génération CV/LM/emails, optionnel brouillon).
    Retourne (result, None) en succès ou (None, message_erreur).
    """
    try:
        base_json = _load_base_json()
    except FileNotFoundError as e:
        return (None, str(e))
    try:
        from core.orchestrator import Orchestrator
        from storage.db import save_application

        orchestrator = Orchestrator(base_json=base_json)
        result = orchestrator.run_pipeline(job_url, create_draft=create_draft)
        save_application(result, job_url, db_path=str(STORAGE_DIR))
        return (result, None)
    except Exception as e:
        log.exception("Pipeline %s", job_url[:60])
        err_msg = f"{type(e).__name__}: {str(e)}" if str(e) else type(e).__name__
        return (None, err_msg)


def _parse_latotale_urls(text: str) -> list[str]:
    """
    Extrait toutes les URLs d'un message /latotale.
    Accepte : une URL, ou plusieurs séparées par des virgules ou des retours à la ligne.
    Découpe uniquement quand une virgule (ou \\n) est suivie d'une nouvelle URL (https?://) pour ne pas casser les paramètres (ex. ?x=1,2).
    """
    urls: list[str] = []
    # Séparer : virgule ou newline suivis d'une URL (lookahead https?://)
    for part in re.split(r"[\n,]\s*(?=https?://)", text, flags=re.IGNORECASE):
        part = part.strip()
        if not part:
            continue
        part = part.rstrip(".,;:)")
        if part.startswith(("http://", "https://")) and part not in urls:
            urls.append(part)
    return urls


@guard
async def cmd_latotale(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    La totale : séquence complète par URL.
    - Une URL  → analyse + scraping + traitement + candidature multicanale (email brouillon) + enregistrement pour relances.
    - Plusieurs URLs (séparées par des virgules ou retours à la ligne) → même séquence pour chaque URL.
    Usage : /latotale <url>   ou   /latotale <url1>, <url2>, <url3>
    """
    text = (update.message.text or "").strip()
    # Enlever la commande pour ne garder que le reste (URLs)
    rest = text[len("/latotale") :].strip() if text.lower().startswith("/latotale") else text
    urls = _parse_latotale_urls(rest)

    if not urls:
        await update.message.reply_text(
            "Usage : /latotale <url>  ou  /latotale <url1>, <url2>, <url3>\n\n"
            "Pour chaque URL : analyse → scraping → traitement → candidature (brouillon email si contact trouvé) → enregistrement pour la séquence de relances J+2, J+4, J+7, J+9."
        )
        return

    n = len(urls)
    await update.message.reply_text(
        f"La totale : {n} URL(s). Séquence complète pour chacune (scraping → traitement → candidature multicanale email + suivi relances)…"
    )

    results_ok = 0
    results_fail = 0
    drafts_created = 0
    lines: list[str] = []
    BATCH_PROGRESS = 5  # un message tous les N URLs pour éviter le flood

    for i, job_url in enumerate(urls):
        try:
            result, err = await asyncio.to_thread(_run_pipeline_sync, job_url, create_draft=True)
        except Exception as e:
            err = str(e)
            result = None
        if err:
            results_fail += 1
            log.warning("Latotale %s: %s", job_url[:50], err)
            lines.append(f"❌ {job_url[:50]}… — {err[:40]}")
        else:
            results_ok += 1
            o = result.offre or {}
            titre = o.get("titre", "?")
            ent = o.get("entreprise", "?")
            action = result.next_action or "?"
            email_dest = (result.email_trouve or {}).get("email_trouve") if isinstance(result.email_trouve, dict) else None
            draft = bool(email_dest and result.next_action == "POSTULER")
            if draft:
                drafts_created += 1
            lines.append(f"✓ {ent} — {titre} | {action}" + (" | Brouillon" if draft else ""))

        if (i + 1) % BATCH_PROGRESS == 0 and (i + 1) < n:
            await update.message.reply_text(f"Traité {i + 1}/{n}…")

    summary = (
        f"La totale terminée : {results_ok} OK, {results_fail} échec(s), {drafts_created} brouillon(s) créé(s).\n\n"
        + "\n".join(lines[:15])
    )
    if len(lines) > 15:
        summary += f"\n… et {len(lines) - 15} autre(s)"
    summary += "\n\nLes candidatures sont enregistrées ; les relances J+2, J+4, J+7, J+9 seront créées (cron ou /relances)."
    await update.message.reply_text(summary[:4000])


@guard
async def cmd_pipeline(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Lance le pipeline de candidature sur une URL.
    Usage : /pipeline <url> [draft]
    Ex. /pipeline https://...  ou  /pipeline https://... draft  (crée le brouillon Gmail)
    """
    text = (update.message.text or "").strip()
    parts = text.split(maxsplit=2)
    if len(parts) < 2:
        await update.message.reply_text(
            "Usage : /pipeline <url> [draft]\n"
            "Ex. /pipeline https://www.welcometothejungle.com/...\n"
            "Avec 'draft' en fin : crée aussi le brouillon Gmail.\n"
            "Tu peux coller une URL de page de recherche (Glassdoor, Indeed, WTTJ, etc.) : les annonces sont extraites et traitées une par une."
        )
        return
    url = parts[1].strip()
    create_draft = len(parts) > 2 and parts[2].lower() == "draft"
    if not url.startswith(("http://", "https://")):
        await update.message.reply_text("L'URL doit commencer par http:// ou https://")
        return

    # Détection page de recherche : extraire les annonces puis traiter chacune
    from scheduler.job_discoverer import is_search_page, extract_job_urls_from_search_page

    if is_search_page(url):
        await update.message.reply_text("Page de recherche détectée. Extraction des annonces...")
        try:
            job_urls = await asyncio.to_thread(extract_job_urls_from_search_page, url, 10)
        except Exception as e:
            await update.message.reply_text(f"Erreur extraction : {e}")
            return
        if not job_urls:
            await update.message.reply_text("Aucune annonce trouvée sur cette page. Le site peut bloquer le scraping (essayez une URL de fiche directe).")
            return
        await update.message.reply_text(f"{len(job_urls)} annonce(s) trouvée(s). Traitement en cours...")
        results_ok = 0
        results_fail = 0
        msgs: list[str] = []
        for i, job_url in enumerate(job_urls):
            try:
                result, err = await asyncio.to_thread(_run_pipeline_sync, job_url, create_draft=False)
            except Exception as e:
                err = str(e)
                result = None
            if err:
                results_fail += 1
                log.warning("Pipeline search item %s: %s", job_url[:50], err)
            else:
                results_ok += 1
                o = result.offre or {}
                m = result.matching or {}
                msgs.append(f"• {o.get('entreprise', '?')} — {o.get('titre', '?')} | {m.get('score', '—')} | {result.next_action}")
            if (i + 1) % 3 == 0:
                await update.message.reply_text(f"Traité {i + 1}/{len(job_urls)}...")
        summary = f"Recherche terminée : {results_ok} OK, {results_fail} échec(s).\n\n" + "\n".join(msgs[:8])
        if len(msgs) > 8:
            summary += f"\n... et {len(msgs) - 8} autre(s)"
        await update.message.reply_text(summary)
        return

    await update.message.reply_text("Pipeline en cours (extraction, matching, génération)...")
    try:
        result, err = await asyncio.to_thread(_run_pipeline_sync, url, create_draft)
    except Exception as e:
        await update.message.reply_text(f"Erreur : {e}")
        return
    if err:
        await update.message.reply_text(f"Échec pipeline : {err}")
        return
    offre = result.offre or {}
    matching = result.matching or {}
    entreprise = offre.get("entreprise", "?")
    titre = offre.get("titre", "?")
    score = matching.get("score", "—")
    action = result.next_action
    msg = f"Pipeline terminé.\n\n{entreprise} — {titre}\nScore : {score} | Action : {action}"
    if create_draft and result.next_action == "POSTULER":
        msg += "\n\nBrouillon Gmail créé."
    if entreprise in ("Entreprise Inconnue", "?", "Non spécifiée", "Inconnue", "Non disponible") or titre in ("Poste Inconnu", "?", "Indisponible"):
        msg += "\n\nSi l'extraction échoue, le site (ex. Indeed) peut bloquer les requêtes. Utilise une URL de fiche d'offre directe (viewjob?jk=...)."
    await update.message.reply_text(msg)


# Mots-clés pour le chatbot (langage naturel)
_PIPELINE_KEYWORDS = (
    "candidater", "candidature", "candidate", "pipeline", "lance", "lancer", "run", "traite", "traiter",
    "cette offre", "cette annonce", "cet offre", "cette url", "ce lien", "pour cette",
    "annonces", "offres", "procédures",
)
_DRAFT_KEYWORDS = ("brouillon", "draft", "gmail", "mail", "email", "envoie", "envoyer", "crée le brouillon")

# Champs JSON typiques pour l'URL d'une offre (priorité à la première occurrence)
_JSON_URL_KEYS = ("url", "link", "job_url", "lien", "apply_url", "job_link", "source_url")


def _find_json_blob(text: str) -> str | None:
    """Retourne le premier blob JSON (à partir de { ou [) ou None."""
    for open_c, close_c in (("{", "}"), ("[", "]")):
        i = text.find(open_c)
        if i == -1:
            continue
        depth = 0
        for j in range(i, len(text)):
            if text[j] == open_c:
                depth += 1
            elif text[j] == close_c:
                depth -= 1
                if depth == 0:
                    try:
                        json.loads(text[i : j + 1])
                        return text[i : j + 1]
                    except json.JSONDecodeError:
                        pass
                    break
    return None


def _urls_from_json_obj(obj: object, urls: list[str]) -> None:
    """Remplit urls avec toutes les chaînes http(s) trouvées récursivement ; privilégie les clés connues."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            key_lower = (k or "").strip().lower()
            if key_lower in _JSON_URL_KEYS and isinstance(v, str) and v.startswith(("http://", "https://")):
                if v not in urls:
                    urls.append(v)
            _urls_from_json_obj(v, urls)
    elif isinstance(obj, list):
        for item in obj:
            _urls_from_json_obj(item, urls)
    elif isinstance(obj, str) and obj.startswith(("http://", "https://")):
        if obj not in urls:
            urls.append(obj)


def _extract_urls_from_json(text: str) -> list[str]:
    """Si le message contient du JSON, en extrait les URLs d'offres (url, link, job_url, lien, etc.)."""
    blob = _find_json_blob(text)
    if not blob:
        return []
    try:
        data = json.loads(blob)
        urls: list[str] = []
        _urls_from_json_obj(data, urls)
        return urls
    except json.JSONDecodeError:
        return []


# URLs : support longues (Glassdoor, LinkedIn, Indeed viewjob), markdown ](url), parenthèses dans le path
def _extract_urls(text: str) -> list[str]:
    urls: list[str] = []
    # 1) Liens markdown ](https://...) avec éventuellement (xx) dans le path
    for m in re.finditer(r"\]\((https?://(?:[^\)]|\([^\)]*\))+)\)", text, re.IGNORECASE):
        u = m.group(1).strip()
        if u and u not in urls:
            urls.append(u)
    # 2) URLs dans un blob JSON (personas[].jobs[].url, offres[].lien, etc.)
    if not urls:
        urls = _extract_urls_from_json(text)
    # 3) URLs brutes : on s'arrête uniquement à l'espace, saut de ligne, tab ou ]
    #    Les virgules, &, =, ? font partie des URLs (ex. Glassdoor KO0,20_KE21,38.htm?jl=...)
    pos = 0
    while True:
        m = re.search(r"https?://", text[pos:], re.IGNORECASE)
        if not m:
            break
        start = pos + m.start()
        end = start + len(m.group(0))
        while end < len(text):
            c = text[end]
            if c in " \t\r\]":
                break
            if c == "\n":
                # URL coupée par un retour à la ligne ? Continuer si la ligne suivante ressemble à la suite de l'URL
                rest = text[end + 1 :].lstrip()
                if rest and (rest[0] in "&=?/" or rest[0].isalnum()):
                    end += 1
                    while end < len(text) and text[end] in " \t":
                        end += 1
                    continue
                break
            end += 1
        u = text[start:end].rstrip(".,;:)")
        if u and u not in urls:
            urls.append(u)
        pos = end
    return urls


def _parse_chat_intent(text: str) -> tuple[str | None, bool]:
    """
    Extrait une URL et l'intention (créer brouillon ou non) depuis un message en langage naturel.
    Retourne (url, create_draft) ou (None, False) si pas d'URL ou pas d'intent pipeline.
    """
    if not text or not text.strip():
        return (None, False)
    t = text.strip().lower()
    urls = _extract_urls(text)
    url = urls[0] if urls else None
    if not url:
        return (None, False)
    want_pipeline = any(kw in t for kw in _PIPELINE_KEYWORDS)
    want_draft = any(kw in t for kw in _DRAFT_KEYWORDS)
    return (url, want_draft) if want_pipeline else (None, False)


# Intent "candidater sur toutes les offres du scan" / "candidate toutes les candidatures"
_PIPELINE_ALL_KEYWORDS = (
    "toutes les offres", "toutes les annonces", "toutes les candidatures",
    "candidate toutes", "candidater sur toutes", "pipeline toutes",
    "dernier scan", "offres du scan", "candidatures du status", "candidatures de /status",
)
# Intent "consulte tous les agents"
_AGENTS_KEYWORDS = ("consulte tous les agents", "liste des agents", "quels agents", "agents disponibles")
# Intent RACI / chef de projet
_RACI_KEYWORDS = ("raci", "chef de projet", "qui fait quoi", "rôles", "responsabilités")


def _parse_intent_with_llm(text: str) -> dict | None:
    """
    Tente l'interprétation LLM. Retourne dict (intent, url, create_draft, response) ou None.
    Exécuter dans asyncio.to_thread car I/O bloquant.
    """
    try:
        base_json = _load_base_json()
    except FileNotFoundError:
        base_json = {}
    from scheduler.chatbot_llm import parse_intent_llm
    return parse_intent_llm(text, base_json)


def _last_scan_job_urls(max_urls: int = 30) -> list[str]:
    """Retourne les URLs d'offres du dernier scan JSON (lien), au plus max_urls."""
    scan_dir = PROJECT_ROOT / "storage" / "scans"
    if not scan_dir.exists():
        return []
    files = list(scan_dir.glob("*.json"))
    if not files:
        return []
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    try:
        data = json.loads(files[0].read_text(encoding="utf-8", errors="replace"))
        offres = data.get("offres", [])[:max_urls]
        return [o.get("lien") for o in offres if o.get("lien") and str(o.get("lien", "")).startswith(("http://", "https://"))]
    except (json.JSONDecodeError, OSError):
        return []


def _agents_message():
    """Message liste des agents (partagé règles + LLM)."""
    return (
        "Agents du système :\n\n"
        "• Scraper — extrait titre, entreprise, description depuis l'URL d'offre\n"
        "• Matching — compare l'offre au profil (persona, score, POSTULER/PASSER)\n"
        "• Generator — produit CV et lettre de motivation ciblés\n"
        "• Drafter — crée le brouillon Gmail avec pièces jointes\n\n"
        "Pour lancer le pipeline : envoie une URL et dis « Candidater sur [url] » ou /pipeline <url> draft"
    )


@guard
async def on_chat_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Chatbot : interprète les messages en langage naturel (LLM + fallback règles).
    Ex. "Candidater sur https://..." ou "Lance le pipeline pour cette offre https://... et crée le brouillon"
    """
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    if text.startswith("/"):
        return
    t = text.lower()

    # 1) Tentative LLM (timeout court pour garder réactivité)
    llm_result = None
    try:
        llm_result = await asyncio.wait_for(
            asyncio.to_thread(_parse_intent_with_llm, text),
            timeout=8.0,
        )
    except (asyncio.TimeoutError, Exception) as e:
        log.debug("LLM intent fallback: %s", e)

    if llm_result and llm_result.get("intent") not in ("unknown", ""):
        intent = llm_result.get("intent", "")
        # Intent RACI : réponse enrichie avec contexte chef de projet
        if intent in ("raci", "agents"):
            resp = (llm_result.get("response") or "").strip()
            await update.message.reply_text(resp[:4000] if resp else _agents_message())
            return
        # Intent help
        if intent == "help":
            resp = (llm_result.get("response") or "").strip()
            await update.message.reply_text(resp[:4000] if resp else "Utilise /help pour l'aide.")
            return
        # Intent pipeline_all
        if intent == "pipeline_all":
            job_urls = _last_scan_job_urls(max_urls=30)
            if not job_urls:
                await update.message.reply_text(
                    "Aucun scan JSON avec offres trouvé. Lance /scan puis attends 2–3 min, puis réessaie."
                )
                return
            await update.message.reply_text(f"Pipeline sur {len(job_urls)} offre(s) du dernier scan…")
            done, failed = 0, 0
            for job_url in job_urls:
                try:
                    result, err = await asyncio.to_thread(_run_pipeline_sync, job_url, create_draft=False)
                    if err:
                        failed += 1
                        log.warning("Pipeline %s : %s", job_url[:50], err)
                    else:
                        done += 1
                        o = (result.offre or {}) if result else {}
                        await update.message.reply_text(f"✓ {o.get('entreprise', '?')} — {o.get('titre', '?')}")
                except Exception as e:
                    failed += 1
                    log.warning("Pipeline %s : %s", job_url[:50], e)
            msg = f"Terminé : {done} traité(s), {failed} échec(s)."
            if done > 0:
                msg += "\n\nLes candidatures sont enregistrées. Pour créer des brouillons Gmail : /pipeline <url> draft sur chaque offre (dossier Brouillons, à envoyer manuellement)."
            await update.message.reply_text(msg)
            return
        # Intent pipeline : utiliser URL du LLM ou extraction regex
        if intent == "pipeline":
            url = llm_result.get("url") or (_extract_urls(text)[0] if _extract_urls(text) else None)
            create_draft = llm_result.get("create_draft", False)
            if url:
                from scheduler.job_discoverer import is_search_page, extract_job_urls_from_search_page
                if is_search_page(url):
                    await update.message.reply_text("Page de recherche détectée. Extraction des annonces...")
                    try:
                        job_urls = await asyncio.to_thread(extract_job_urls_from_search_page, url, 10)
                    except Exception as e:
                        await update.message.reply_text(f"Erreur extraction : {e}")
                        return
                    if not job_urls:
                        await update.message.reply_text("Aucune annonce trouvée sur cette page.")
                        return
                    await update.message.reply_text(f"{len(job_urls)} annonce(s). Traitement en cours...")
                    done, failed = 0, 0
                    msgs = []
                    for i, ju in enumerate(job_urls):
                        try:
                            result, err = await asyncio.to_thread(_run_pipeline_sync, ju, create_draft=False)
                        except Exception as e:
                            err = str(e)
                            result = None
                        if err:
                            failed += 1
                        else:
                            done += 1
                            o = (result.offre or {}) if result else {}
                            msgs.append(f"• {o.get('entreprise', '?')} — {o.get('titre', '?')}")
                        if (i + 1) % 3 == 0:
                            await update.message.reply_text(f"Traité {i + 1}/{len(job_urls)}...")
                    await update.message.reply_text(f"Terminé : {done} OK, {failed} échec(s).\n" + "\n".join(msgs[:8]))
                    return
                await update.message.reply_text("Pipeline en cours (extraction, matching, génération)...")
                try:
                    result, err = await asyncio.to_thread(_run_pipeline_sync, url, create_draft)
                except Exception as e:
                    await update.message.reply_text(f"Erreur : {e}")
                    return
                if err:
                    await update.message.reply_text(f"Échec pipeline : {err}")
                    return
                offre = (result.offre or {}) if result else {}
                matching = (result.matching or {}) if result else {}
                msg = f"Pipeline terminé.\n\n{offre.get('entreprise', '?')} — {offre.get('titre', '?')}\nScore : {matching.get('score', '—')} | Action : {result.next_action}"
                if create_draft and result.next_action == "POSTULER":
                    msg += "\n\nBrouillon Gmail créé."
                await update.message.reply_text(msg)
                return

    # 2) Fallback règles (keywords)
    if any(kw in t for kw in _RACI_KEYWORDS):
        try:
            from scheduler.chatbot_llm import _get_raci_context
            base = _load_base_json()
            raci_text = _get_raci_context(base)
            await update.message.reply_text(raci_text[:4000] if raci_text else _agents_message())
        except Exception:
            await update.message.reply_text(_agents_message())
        return

    if any(kw in t for kw in _AGENTS_KEYWORDS):
        await update.message.reply_text(_agents_message())
        return

    if any(kw in t for kw in _PIPELINE_ALL_KEYWORDS):
        job_urls = _last_scan_job_urls(max_urls=30)
        if not job_urls:
            await update.message.reply_text(
                "Aucun scan JSON avec offres trouvé. Lance /scan puis attends 2–3 min, puis réessaie."
            )
            return
        await update.message.reply_text(f"Pipeline sur {len(job_urls)} offre(s) du dernier scan…")
        done, failed = 0, 0
        for job_url in job_urls:
            try:
                result, err = await asyncio.to_thread(_run_pipeline_sync, job_url, create_draft=False)
                if err:
                    failed += 1
                    log.warning("Pipeline %s : %s", job_url[:50], err)
                else:
                    done += 1
                    o = (result.offre or {}) if result else {}
                    await update.message.reply_text(f"✓ {o.get('entreprise', '?')} — {o.get('titre', '?')}")
                except Exception as e:
                    failed += 1
                    log.warning("Pipeline %s : %s", job_url[:50], e)
        msg = f"Terminé : {done} traité(s), {failed} échec(s)."
        if done > 0:
            msg += "\n\nPour des brouillons Gmail : /pipeline <url> draft sur chaque offre."
        await update.message.reply_text(msg)
        return

    url, create_draft = _parse_chat_intent(text)
    if url:
        from scheduler.job_discoverer import is_search_page, extract_job_urls_from_search_page
        if is_search_page(url):
            await update.message.reply_text("Page de recherche détectée. Extraction des annonces...")
            try:
                job_urls = await asyncio.to_thread(extract_job_urls_from_search_page, url, 10)
            except Exception as e:
                await update.message.reply_text(f"Erreur extraction : {e}")
                return
            if not job_urls:
                await update.message.reply_text("Aucune annonce trouvée sur cette page.")
                return
            await update.message.reply_text(f"{len(job_urls)} annonce(s). Traitement en cours...")
            done, failed = 0, 0
            msgs = []
            for i, ju in enumerate(job_urls):
                try:
                    result, err = await asyncio.to_thread(_run_pipeline_sync, ju, create_draft=False)
                except Exception as e:
                    err = str(e)
                    result = None
                if err:
                    failed += 1
                else:
                    done += 1
                    o = (result.offre or {}) if result else {}
                    msgs.append(f"• {o.get('entreprise', '?')} — {o.get('titre', '?')}")
                if (i + 1) % 3 == 0:
                    await update.message.reply_text(f"Traité {i + 1}/{len(job_urls)}...")
            await update.message.reply_text(f"Terminé : {done} OK, {failed} échec(s).\n" + "\n".join(msgs[:8]))
            return
    if not url:
        want_candidate = any(kw in t for kw in _PIPELINE_KEYWORDS) or "candidate" in t
        if want_candidate and _find_json_blob(text):
            await update.message.reply_text(
                "Ce JSON ne contient pas d'URLs d'offres.\n\n"
                "Pour candidater, il faut le lien vers la fiche (LinkedIn, Indeed, Glassdoor, etc.). "
                "Ajoute un champ à chaque offre : \"url\", \"link\", \"job_url\" ou \"lien\".\n\n"
                "Ex. : \"company\": \"InfraSys\", \"title\": \"...\", \"url\": \"https://linkedin.com/jobs/...\"\n\n"
                "Tu peux aussi envoyer directement une ou plusieurs URLs avec « Candidater sur [url] »."
            )
            return
        await update.message.reply_text(
            "Tu peux m’envoyer une URL d’offre et par exemple :\n"
            "• « Candidater sur [url] »\n"
            "• « Lance le pipeline pour [url] »\n"
            "• « Candidater sur [url] et crée le brouillon Gmail »\n\n"
            "• « Candidater sur toutes les offres du scan »\n"
            "• « Consulte tous les agents » / « Qui fait quoi ? » (RACI)\n\n"
            "Ou : /pipeline <url> draft"
        )
        return
    await update.message.reply_text("Pipeline en cours (extraction, matching, génération)...")
    try:
        result, err = await asyncio.to_thread(_run_pipeline_sync, url, create_draft)
    except Exception as e:
        await update.message.reply_text(f"Erreur : {e}")
        return
    if err:
        await update.message.reply_text(f"Échec pipeline : {err}")
        return
    offre = result.offre or {}
    matching = result.matching or {}
    entreprise = offre.get("entreprise", "?")
    titre = offre.get("titre", "?")
    score = matching.get("score", "—")
    action = result.next_action
    msg = f"Pipeline terminé.\n\n{entreprise} — {titre}\nScore : {score} | Action : {action}"
    if create_draft and result.next_action == "POSTULER":
        msg += "\n\nBrouillon Gmail créé."
    if entreprise in ("Entreprise Inconnue", "?", "Non spécifiée", "Inconnue", "Non disponible") or titre in ("Poste Inconnu", "?", "Indisponible"):
        msg += "\n\nSi l'extraction échoue, le site (ex. Indeed) peut bloquer les requêtes. Utilise une URL de fiche d'offre directe (viewjob?jk=...)."
    await update.message.reply_text(msg)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Répond toujours : si non autorisé, envoie ton ID pour que tu l'ajoutes au .env (aucun bot tiers)."""
    try:
        user = update.effective_user
        if not user:
            return
        user_id = user.id
        if rate_limited(user_id):
            await update.message.reply_text("Rate limit atteint.")
            return
        if is_allowed(user_id):
            await update.message.reply_text("Bot actif.")
            log.info("CMD start — user=%s", user_id)
            return
        # Pas encore autorisé : on lui donne son ID pour qu'il l'ajoute au .env (pas de bot tiers)
        await update.message.reply_text(
            f"Ton ID Telegram : {user_id}\n\n"
            f"Ajoute dans ton fichier .env :\n"
            f"TELEGRAM_ALLOWED_IDS={user_id}\n\n"
            f"Puis redémarre le bot. Ensuite /start répondra « Bot actif. »"
        )
        log.info("ID envoyé à user=%s (pas encore autorisé)", user_id)
    except Exception as e:
        log.exception("cmd_start")
        try:
            await update.message.reply_text(f"Erreur : {e}")
        except Exception:
            pass


@guard
async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        if not Path(DB_PATH).exists():
            await update.message.reply_text("Aucune candidature en base.")
            return

        def _fetch() -> list:
            conn = sqlite3.connect(DB_PATH, timeout=5.0)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT job_url, score, status, result_json, created_at FROM applications "
                "ORDER BY created_at DESC LIMIT 10"
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]

        rows = await asyncio.to_thread(_fetch)

        if not rows:
            await update.message.reply_text("Aucune candidature en base.")
            return

        statut_emoji = {"J0": "📤", "relance_j4": "🔔", "relance_j10": "🔕", "envoyee": "📤"}
        msg = "Candidatures recentes\n\n"
        for r in rows:
            try:
                data = json.loads(r.get("result_json") or "{}")
                offre = data.get("offre", {})
                entreprise = offre.get("entreprise") or "?"
                titre = offre.get("titre") or "?"
                if entreprise == "?" and titre == "?":
                    url = r.get("job_url") or ""
                    if url:
                        try:
                            dom = urlparse(url).netloc or url[:40]
                            titre = dom.replace("www.", "") if len(dom) > 2 else url[:35] + "…"
                        except Exception:
                            titre = url[:40] + "…" if len(url) > 40 else url
            except (json.JSONDecodeError, TypeError):
                entreprise, titre = "?", "?"
            emoji = statut_emoji.get(r.get("status", ""), "•")
            score_str = f"{r.get('score')}/100" if r.get("score") is not None else "—"
            date_str = (r.get("created_at") or "")[:10]
            msg += f"{emoji} {entreprise}\n  {titre} | Score: {score_str} | {date_str}\n\n"

        await update.message.reply_text(msg)
    except Exception as e:
        log.exception("cmd_status")
        await update.message.reply_text(f"Erreur : {e}")


@guard
async def cmd_offres(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        scan_dir = PROJECT_ROOT / "storage" / "scans"
        if not scan_dir.exists():
            await update.message.reply_text("Aucun scan disponible.")
            return
        files = sorted(scan_dir.glob("*.csv"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not files:
            files = list(scan_dir.glob("*.json"))
            files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        if not files:
            await update.message.reply_text("Aucun scan disponible.")
            return

        latest = files[0]
        text = await asyncio.to_thread(lambda: latest.read_text(encoding="utf-8", errors="replace"))
        if latest.suffix == ".json":
            try:
                data = json.loads(text)
                meta = data.get("metadata", {})
                offres = data.get("offres", [])[:20]
                total = meta.get("nombre_offres", len(data.get("offres", [])))
                msg = f"Dernier scan : {latest.name}\nTotal : {total} offre(s)\n\n"
                for o in offres:
                    ent, tit = o.get("entreprise", "?"), o.get("titre", "?")
                    if ent in ("?", "Entreprise Inconnue") and tit in ("?", "Poste Inconnu"):
                        lien = (o.get("lien") or "")[:55]
                        if lien:
                            msg += f"• {lien}… | {o.get('score_pct','')}%\n"
                        else:
                            msg += f"• {ent} — {tit} | {o.get('score_pct','')}%\n"
                    else:
                        msg += f"• {ent} — {tit} | {o.get('score_pct','')}%\n"
                if not offres:
                    msg += "Aucune offre affichée (liste vide ou tout déjà vu)."
            except json.JSONDecodeError:
                msg = "Fichier JSON invalide."
        else:
            lines = text.splitlines()
            msg = f"Dernieres offres ({latest.name})\n\n"
            header = lines[0].split(",") if lines else []
            for line in lines[1:11]:
                parts = line.split(",")
                if len(parts) >= 3:
                    msg += f"• {parts[1]} — {parts[2]} | {parts[7] if len(parts) > 7 else ''}\n"

        await update.message.reply_text(msg[:4000])
    except Exception as e:
        log.exception("cmd_offres")
        await update.message.reply_text(f"Erreur : {e}")


@guard
async def cmd_relances(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        if not Path(DB_PATH).exists():
            await update.message.reply_text("Aucune relance en attente.")
            return

        def _fetch():
            conn = sqlite3.connect(DB_PATH, timeout=5.0)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT result_json, created_at, status FROM applications "
                "WHERE status IN ('J0', 'envoyee', 'relance_j4') AND result_json IS NOT NULL"
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]

        rows = await asyncio.to_thread(_fetch)
        today = datetime.now().date()
        msg = "Relances a venir\n\n"
        count = 0
        for r in rows:
            try:
                data = json.loads(r.get("result_json") or "{}")
                offre = data.get("offre", {})
                canal = data.get("canal_application", {})
                entreprise = offre.get("entreprise", "?")
                titre = offre.get("titre", "?")
                email = canal.get("contact_cible", "")
                if not email or email == "Inconnu":
                    continue
                date_str = (r.get("created_at") or "")[:10]
                date_cand = datetime.fromisoformat(date_str).date()
                delta = (today - date_cand).days
                j4 = date_cand + timedelta(days=4)
                j10 = date_cand + timedelta(days=10)

                if delta < 4:
                    msg += f"J+4 le {j4} — {entreprise}\n"
                elif delta == 4:
                    msg += f"J+4 AUJOURD'HUI — {entreprise}\n"
                elif r.get("status") == "relance_j4" and delta < 10:
                    msg += f"J+10 le {j10} — {entreprise}\n"
                elif r.get("status") == "relance_j4" and delta >= 10:
                    msg += f"J+10 AUJOURD'HUI — {entreprise}\n"
                count += 1
            except (ValueError, KeyError, TypeError):
                continue

        if count == 0:
            msg = "Aucune relance en attente."
        await update.message.reply_text(msg[:4000])
    except Exception as e:
        log.exception("cmd_relances")
        await update.message.reply_text(f"Erreur : {e}")


@guard
async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        if not Path(DB_PATH).exists():
            await update.message.reply_text("Aucune donnee.")
            return

        def _fetch():
            conn = sqlite3.connect(DB_PATH, timeout=5.0)
            total = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
            par_statut = conn.execute(
                "SELECT status, COUNT(*) FROM applications GROUP BY status"
            ).fetchall()
            score_row = conn.execute("SELECT AVG(score) FROM applications").fetchone()
            conn.close()
            return total, par_statut, score_row

        total, par_statut, score_row = await asyncio.to_thread(_fetch)

        score_moy = score_row[0] if score_row and score_row[0] is not None else None
        msg = f"Statistiques\n\nTotal : {total}\nScore moyen : {round(score_moy, 1) if score_moy else '—'}/100\n\nPar statut :\n"
        for statut, cnt in par_statut:
            msg += f"  • {statut} : {cnt}\n"
        await update.message.reply_text(msg)
    except Exception as e:
        log.exception("cmd_stats")
        await update.message.reply_text(f"Erreur : {e}")


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")[:3500]


@guard
async def cmd_logs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    content = await asyncio.to_thread(tail_log, LOG_PATH, 25)
    content = _escape_html(content)
    await update.message.reply_text(f"<pre>{content}</pre>", parse_mode="HTML")


@guard
async def cmd_followup_logs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    content = await asyncio.to_thread(tail_log, FOLLOWUP_LOG, 20)
    content = _escape_html(content)
    await update.message.reply_text(f"<pre>{content}</pre>", parse_mode="HTML")


@guard
async def cmd_scan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("Confirmer", callback_data="scan_confirm"),
            InlineKeyboardButton("Annuler", callback_data="scan_cancel"),
        ]
    ]
    await update.message.reply_text(
        "Lancer un scan (Indeed, France Travail, HelloWork, Dogfinance, Meteojob, Glassdoor, LinkedIn, WTTJ, APEC) ?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def callback_scan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    if not user or user.id not in ALLOWED_USER_IDS:
        await query.edit_message_text("Acces non autorise.")
        return

    if query.data == "scan_cancel":
        await query.edit_message_text("Scan annule.")
        return

    await query.edit_message_text("Scan en cours...")
    log.info("Scan manuel declenche par user=%s", user.id)

    sources = "wttj,francetravail,indeed,hellowork,dogfinance,meteojob,glassdoor,linkedin,apec,manpower,adecco"
    try:
        log_file = LOGS_DIR / "manual_scan.log"
        (PROJECT_ROOT / "storage" / "scans").mkdir(parents=True, exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as f:
            # 1) job_scanner_runner écrit dans storage/scans/ → /offres pourra afficher les offres
            subprocess.Popen(
                [
                    sys.executable, "-m", "scheduler.job_scanner_runner",
                    "--sources", sources,
                    "--format", "json",
                    "--max", "10",
                ],
                cwd=str(PROJECT_ROOT),
                stdout=f,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            # 2) cron_runner pour le pipeline complet (candidatures, relances)
            subprocess.Popen(
                [
                    sys.executable, "-m", "scheduler.cron_runner",
                    "--mode", "both",
                    "--sources", sources,
                    "--max", "10",
                ],
                cwd=str(PROJECT_ROOT),
                stdout=f,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        await ctx.bot.send_message(
            chat_id=query.message.chat_id,
            text="Scan lance (scanner + pipeline). /offres dans 2–3 min pour les offres. /logs pour les resultats.",
        )
    except Exception as e:
        log.exception("callback_scan")
        await ctx.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"Erreur lancement scan : {e}",
        )


@guard
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = (
        "Job Search Agent — Panneau de controle\n\n"
        "Tu peux discuter en langage naturel : envoie une URL et dis par ex. "
        "« Candidater sur [url] » ou « Lance le pipeline pour [url] et crée le brouillon ».\n\n"
        "/latotale <url> ou <url1>, <url2>, … — Séquence complète par URL : analyse, scraping, traitement, candidature (email), enregistrement relances J+2/J+4/J+7/J+9\n"
        "/pipeline <url> [draft] — Lancer l'orchestrateur. Accepte une fiche d'offre ou une page de recherche (annonces extraites puis traitées)\n"
        "/status — Candidatures recentes\n"
        "/offres — Dernieres offres scannees\n"
        "/relances — Relances J+4/J+10 a venir\n"
        "/scan — Lancer un scan manuel\n"
        "/logs — Dernieres lignes cron.log\n"
        "/followup_logs — Logs relances\n"
        "/stats — Statistiques globales\n"
        "/help — Cette aide\n"
    )
    await update.message.reply_text(msg)


async def _error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Capture les erreurs non gérées pour éviter que le bot crash."""
    log.exception("Erreur non geree : %s", ctx.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("Erreur interne. Verifie les logs.")
        except Exception:
            pass


def main():
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN manquant dans .env")

    log.info("Bot demarre — users autorises : %s (envoie /start a ton bot pour obtenir ton ID)", ALLOWED_USER_IDS or "aucun")

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .get_updates_connect_timeout(30)
        .get_updates_read_timeout(60)
        .build()
    )
    app.add_error_handler(_error_handler)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("latotale", cmd_latotale))
    app.add_handler(CommandHandler("pipeline", cmd_pipeline))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("offres", cmd_offres))
    app.add_handler(CommandHandler("relances", cmd_relances))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("logs", cmd_logs))
    app.add_handler(CommandHandler("followup_logs", cmd_followup_logs))
    app.add_handler(CommandHandler("scan", cmd_scan))
    app.add_handler(CallbackQueryHandler(callback_scan, pattern="^scan_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_chat_message))

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
