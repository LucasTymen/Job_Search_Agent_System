"""
Orchestrateur Hybrid - Combine extraction LLM et matching déterministe Python.
"""
import os
import re
import json
from datetime import datetime, timedelta
from urllib.parse import urlparse
from core.models import FinalOutput, ScraperOutput, MatchingOutput, ATVCheck
from core.utils import sanitize_placeholders, attachment_filenames
from core.atv_validator import valider_donnees
from agents.scraper import ScraperOffre, EntrepriseScraper
from agents.matching import MatchingEngine
from agents.generator import CvAtvGenerator, LmCoordinator, EmailEngine
from agents.drafting import GmailDraftingAgent
from agents.cv_pdf import CvPdfGenerator


def _fallback_email_from_url(job_url: str) -> str | None:
    """
    Dérive un email de fallback (recrutement@domaine) à partir de l'URL d'offre
    pour permettre la création du brouillon quand EntrepriseScraper ne trouve pas d'email.
    L'utilisateur pourra corriger le destinataire dans Gmail si besoin.
    """
    if not job_url or not job_url.strip():
        return None
    try:
        parsed = urlparse(job_url)
        path = (parsed.path or "").strip("/")
        host = (parsed.netloc or "").lower()
        slug = None
        if "lever.co" in host:
            parts = path.split("/")
            if len(parts) >= 1 and parts[0]:
                slug = parts[0]
        elif "ashbyhq.com" in host:
            parts = path.split("/")
            if len(parts) >= 1 and parts[0]:
                slug = parts[0]
        elif "welcometothejungle.com" in host:
            m = re.search(r"/companies/([^/]+)/", path)
            if m:
                slug = m.group(1)
        elif "greenhouse.io" in host:
            parts = path.split("/")
            for i, p in enumerate(parts):
                if p == "jobs" and i > 0:
                    slug = parts[i - 1]
                    break
            if not slug and parts:
                slug = parts[0]
        if slug and re.match(r"^[a-z0-9][a-z0-9.-]*$", slug, re.I):
            return f"recrutement@{slug}.com"
    except Exception:
        pass
    return None

class Orchestrator:
    def __init__(self, base_json: dict):
        self.base_json = base_json
        self.scraper = ScraperOffre()
        self.entreprise_scraper = EntrepriseScraper()
        self.matching = MatchingEngine(base_json=base_json)
        self.cv_gen = CvAtvGenerator(base_json=base_json)
        self.lm_gen = LmCoordinator(base_json=base_json)
        self.email_gen = EmailEngine(base_json=base_json)
        self.drafter = GmailDraftingAgent()

    def run_pipeline(self, job_url: str, create_draft: bool = False, email_override: str | None = None) -> FinalOutput:
        print(f"--- Pipeline démarrée pour : {job_url} ---")
        
        # 1. Extraction (GROQ/LLM uniquement sur texte public)
        print("Étape 1: Extraction des données de l'offre...")
        job_data = self.scraper.process(job_url)
        print(f"Offre : {job_data.titre} @ {job_data.entreprise}")

        # 2. Matching Déterministe (PYTHON PUR)
        print("Étape 2: Matching stratégique (Python)...")
        match_data = self.matching.process(job_data)
        print(f"Persona : {match_data.persona_selectionne} (Score: {match_data.score})")

        # 3. Extraction Entreprise (email pour brouillon + relances)
        entreprise_data = self.entreprise_scraper.process(job_url)
        if email_override and str(email_override).strip():
            entreprise_data = dict(entreprise_data)
            entreprise_data["email_trouve"] = email_override.strip()
        elif not entreprise_data.get("email_trouve"):
            fallback = _fallback_email_from_url(job_url)
            if fallback:
                entreprise_data = dict(entreprise_data)
                entreprise_data["email_trouve"] = fallback

        # 4. Génération (GROQ/LLM sur profil ANONYMISÉ)
        print("Étape 3: Génération des assets humanisés...")
        offre_d = job_data.model_dump()
        contact_name = entreprise_data.get("contact_name") or entreprise_data.get("recruteur")
        cv_data = self.cv_gen.process(match_data, offre=offre_d)
        cv_markdown = self.cv_gen.render_cv_markdown(cv_data, offre=offre_d, final=True)
        lm_text = self.lm_gen.process(match_data, offre=offre_d, contact_name=contact_name)
        emails = self.email_gen.process(match_data, offre=offre_d, contact_name=contact_name)

        # Validation ATV (anti-hallucination) sur CV et LM
        atv_ok_cv, atv_msg_cv = valider_donnees(self.base_json, cv_markdown)
        atv_ok_lm, atv_msg_lm = valider_donnees(self.base_json, lm_text)
        atv_ok = atv_ok_cv and atv_ok_lm
        atv_comment = "Validation OK" if atv_ok else f"CV: {atv_msg_cv} | LM: {atv_msg_lm}"

        output = FinalOutput(
            offre=offre_d,
            matching=match_data.model_dump(),
            documents={
                "cv": cv_markdown,
                "lm": lm_text
            },
            canal_application={
                "canal_recommande": "Email direct",
                "contact_cible": entreprise_data.get("email_trouve") or "Inconnu"
            },
            email_trouve={k: str(v) for k, v in entreprise_data.items()},
            emails=emails or {},
            next_action=match_data.next_action,
            date_relance_j2=(datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d'),
            date_relance_j4=(datetime.now() + timedelta(days=4)).strftime('%Y-%m-%d'),
            date_relance_j7=(datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d'),
            date_relance_j9=(datetime.now() + timedelta(days=9)).strftime('%Y-%m-%d'),
            ATV_CHECK=ATVCheck(
                donnees_verifiees=atv_ok,
                hallucination_detectee=not atv_ok,
                commentaire=atv_comment
            )
        )

        # 5. Draft Gmail (Optionnel) — écriture CV/LM sur disque puis brouillon
        email_dest = entreprise_data.get("email_trouve")
        if create_draft and match_data.next_action == "POSTULER" and email_dest:
            titre = job_data.titre or ""
            entreprise = job_data.entreprise or ""
            reference = offre_d.get("reference", "")
            contact_name = contact_name or ""
            raw_sujet = emails.get("sujet") or f"Candidature - {titre}"
            raw_body = emails.get("email_j0") or ""
            sujet = sanitize_placeholders(raw_sujet, titre_poste=titre, entreprise=entreprise, reference=reference, prenom_recruteur=contact_name)
            body = sanitize_placeholders(raw_body, titre_poste=titre, entreprise=entreprise, reference=reference, prenom_recruteur=contact_name)
            if not sujet.strip():
                sujet = f"Candidature - {titre}" if titre else "Candidature"
            if not body.strip():
                body = "Monsieur, Madame,\n\nVeuillez trouver ci-joint ma candidature.\n\nCordialement,\nLucas Tymen"
            cv_name, lm_name = attachment_filenames(entreprise, titre)
            out_dir = getattr(self, "_output_dir", None) or os.path.join(os.path.dirname(os.path.dirname(__file__)), "outputs")
            os.makedirs(os.path.join(out_dir, "cvs"), exist_ok=True)
            os.makedirs(os.path.join(out_dir, "lms"), exist_ok=True)
            pdf_gen = CvPdfGenerator(output_dir=out_dir)
            cv_path = pdf_gen.generate(cv_name, cv_data)
            lm_path = pdf_gen.generate_lm(lm_name, lm_text)
            attachment_paths = [p for p in [cv_path, lm_path] if p and os.path.exists(p)]
            self.drafter.create_draft(
                email_dest,
                sujet,
                body,
                attachment_paths
            )
            print("Brouillon créé avec succès.")

        return output
