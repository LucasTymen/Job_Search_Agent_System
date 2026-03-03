"""
Agents de génération (CV, LM, Email) raffinés avec protection PII stricte.
"""
import json
from core.models import MatchingOutput
from core.llm_client import OpenAIClient

ANTI_AI_PROMPT = """
Tu es un correcteur éditorial expert dans la détection et la neutralisation des marqueurs de texte générés par intelligence artificielle.
Ton rôle est d'adopter un ton humain, nuancé, fluide, sans structure artificielle, ni marqueurs typiques de génération LLM.
"""

# Directives communes pour les agents de rédaction (lettre de motivation + emails)
REDACTION_DIRECTIVES = """
DIRECTIVES DE TON ET FORME (lettres et emails) :
- Conserver la tonalité anti-IA (pas de formules génériques type LLM).
- Ton formel mais un peu chaleureux. Dynamique et positif. Très axé data-driven.
- Zéro hallucination : n'utiliser que les données fournies. Ton décontracté à éviter (max ~1%).
- Ne jamais utiliser d'accroches du type « Bonjour », « J'espère que vous allez bien », etc.
- Formule de courtoisie : « Monsieur, Madame, » en tête. Personnaliser si l'auteur de l'annonce est connu (nom du recruteur) avec un ice-breaker discret si pertinent.
- Structure : 1) centrer sur les besoins de l'entreprise ; 2) en seconde partie, présenter les solutions que j'apporte, argumentées (chiffres, faits issus des briques fournies).
- Longueur : court. Maximum une vingtaine à trentaine de lignes.
- Citer obligatoirement la référence de l'annonce et l'intitulé du poste soit dans le corps du texte (début) soit dans l'objet (pour les emails).
- Ne jamais écrire de placeholders du type {{titre_poste}} ou {{prenom_recruteur}}. Utiliser uniquement les valeurs fournies dans le prompt ; si une donnée manque, l'omettre (phrase courte sans accolade ni chaîne vide).
"""

def _minify_json_safe(data: dict, remove_pii: bool = True) -> str:
    """
    Purge TOUT ce qui est identifiable : meta, narratifs persos, arguments personnalisés.
    Ne garde que les 'briques' techniques et professionnelles neutres.
    """
    minified = {
        "experiences": [],
        "arguments_competences": []
    }
    
    for exp in data.get("experiences", []):
        minified["experiences"].append({
            "entite": exp.get("entite"),
            "role": exp.get("role") or exp.get("role_it"),
            "periode": exp.get("periode"),
            "points_cles": exp.get("bullet_cv_court")
        })
        
    for group, args in data.get("arguments_reutilisables", {}).items():
        if isinstance(args, list):
            for item in args:
                if isinstance(item, dict) and "argument" in item:
                    minified["arguments_competences"].append(item.get("argument"))
            
    return json.dumps(minified, ensure_ascii=False)

# Structure de rédaction du CV (format markdown strict)
DEFAULT_LANDING_PAGE = "https://lppp-infopro.vercel.app/"


class CvAtvGenerator:
    """
    Générateur de structure de CV (logique déterministe) et rédaction au format markdown strict.
    Structure de sortie : titre poste, référence annonce, entreprise, cartouche, PROFIL,
    COMPETENCES PRINCIPALES, OUTILS, EXPERIENCE, FORMATION, Soft skills, LANGUES, DISPONIBILITE.
    """
    def __init__(self, base_json: dict):
        self.base_json = base_json

    def process(self, matching_data: MatchingOutput, offre: dict = None) -> dict:
        meta = self.base_json.get("meta", {})
        cv_data = {
            "nom": meta.get("nom", "Lucas Tymen"),
            "adresse": meta.get("adresse", ""),
            "telephone": meta.get("telephone", ""),
            "email": meta.get("email", ""),
            "linkedin": meta.get("linkedin", ""),
            "landing_page": meta.get("landing_page", DEFAULT_LANDING_PAGE),
            "titre_poste": (offre or {}).get("titre") or matching_data.persona_selectionne,
            "reference_annonce": (offre or {}).get("reference", ""),
            "nom_entreprise": (offre or {}).get("entreprise", ""),
            "profil": self.base_json.get("narratifs_candidature", {}).get(self._get_narratif_key(matching_data), ""),
            "experiences": [],
            "competences_ats": {"Compétences": matching_data.mots_cles_ats},
            "formation": [],
            "langues": [],
            "competences_principales": [],
            "outils": [],
            "soft_skills": [],
            "disponibilite": "",
        }
        # Expériences (période et bullets selon secteur ; filtre par secteur pour it_support)
        secteur = matching_data.secteur_detecte
        for exp in self.base_json.get("experiences", []):
            # it_support : n'afficher que les expériences pertinentes (principale/secondaire)
            if secteur == "it_support":
                priorite = (exp.get("priorite_secteur") or {}).get("it_support", "")
                if priorite not in ("principale", "secondaire"):
                    continue
            # A.P.S.I. : toujours 2015–2022 (CV rajeuni, psychologie à partir de 2015)
            periode = exp.get("periode") or (
                exp.get("periode_it") if secteur == "it_support" else exp.get("periode_growth") or exp.get("periode_it")
            )
            raw_bullets = exp.get("bullet_cv_court", [])
            if isinstance(raw_bullets, dict):
                bullets = (
                    raw_bullets.get("version_operationnelle") if secteur == "it_support"
                    else raw_bullets.get("version_strategique")
                ) or (list(raw_bullets.values())[0] if raw_bullets else [])
                bullets = bullets if isinstance(bullets, list) else [str(bullets)]
            else:
                bullets = raw_bullets if isinstance(raw_bullets, list) else []
            cv_data["experiences"].append({
                "entite": exp.get("entite", ""),
                "role": exp.get("role") or exp.get("role_it"),
                "periode": periode,
                "bullets": bullets,
                "_ordre_secteur": 0 if (secteur == "it_support" and ("A.P.S.I." in (exp.get("entite") or "") or "Responsable IT" in str(exp.get("role") or ""))) else 1,
            })
        if secteur == "it_support":
            cv_data["experiences"].sort(key=lambda e: e.get("_ordre_secteur", 1))
        for e in cv_data["experiences"]:
            e.pop("_ordre_secteur", None)
        # Formations (base_real : intitule, periode, type, note)
        for f in self.base_json.get("formations", self.base_json.get("formation", [])):
            intitule = f.get("intitule", "")
            note = f.get("note", "")
            details = note if isinstance(note, list) else ([note] if note else [])
            # Établissement parfois au début de intitule (ex: "M2i – Licence Pro...")
            etab = f.get("etablissement", "")
            if not etab and " – " in intitule:
                etab, intitule = intitule.split(" – ", 1)
            cv_data["formation"].append({
                "etablissement": etab,
                "niveau": f.get("niveau", f.get("type", "")),
                "intitule": intitule,
                "annee": f.get("periode", f.get("annee", "")),
                "details": details
            })
        # Langues
        for lg in self.base_json.get("langues", []):
            cv_data["langues"].append({
                "langue": lg.get("langue", ""),
                "niveau": lg.get("niveau", ""),
                "detail": lg.get("note", "")
            })
        # Compétences principales (base_json ou dérivées de competences_detaillees pour it_support)
        for cp in self.base_json.get("competences_principales", []):
            cv_data["competences_principales"].append({
                "nom": cp.get("nom", cp.get("titre", "")),
                "details": cp.get("details", cp.get("bullet_cv_court", []))
            })
        if not cv_data["competences_principales"] and secteur == "it_support":
            cd = self.base_json.get("competences_detaillees", {}).get("it_support_systemes", {})
            if cd:
                details = list(cd.get("outils", [])) + list(cd.get("cas_usage_securite", []))
                if details:
                    cv_data["competences_principales"].append({"nom": "Support et Systèmes", "details": details})
                cv_data["soft_skills"] = list(cd.get("soft_skills", []))
        if not cv_data["competences_principales"] and matching_data.mots_cles_ats:
            cv_data["competences_principales"].append({
                "nom": "Compétences principales",
                "details": list(matching_data.mots_cles_ats)
            })
        # Outils (liste ou dérivée des mots-clés ATS)
        cv_data["outils"] = self.base_json.get("outils", []) or list(matching_data.mots_cles_ats)
        # Soft skills & disponibilité (déjà rempli pour it_support ci-dessus si competences_detaillees)
        if not cv_data["soft_skills"]:
            cv_data["soft_skills"] = self.base_json.get("soft_skills", [])
        disp = self.base_json.get("disponibilite", {})
        if isinstance(disp, dict):
            cv_data["disponibilite"] = f"{disp.get('zone', 'Paris')}, {disp.get('teletravail', 'présentiel')}, {disp.get('disponibilite', 'Disponible')}"
        else:
            cv_data["disponibilite"] = str(disp or "Paris, présentiel, Disponible")
        return cv_data

    def render_cv_markdown(self, cv_data: dict, offre: dict = None, final: bool = False) -> str:
        """
        Rédaction du CV au format markdown (structure imposée).
        Si final=True : sortie « finalisée » sans lignes #, cartouche téléphone/email sur 2 lignes, section ATOUTS.
        """
        import re
        o = offre or {}
        ref = cv_data.get("reference_annonce") or o.get("reference", "—")
        entreprise = cv_data.get("nom_entreprise") or o.get("entreprise", "—")
        ville_cp = (cv_data.get("adresse") or "").replace("(", " ").replace(")", " ")
        ville_cp = re.sub(r"\s+", " ", ville_cp).strip().rstrip(" .") or "Maisons-Alfort 94700"
        landing = cv_data.get("landing_page", DEFAULT_LANDING_PAGE)

        def L(*parts):
            return [] if final else list(parts)

        lines = (
            L("# titre : poste visé")
            + [f"**{cv_data.get('titre_poste', '')}**", ""]
            + L("# Référence de l'annonce")
            + [f"Reference annonce **{ref}**"]
            + L("# nom de l'entreprise")
            + [f"Entreprise {entreprise}", ""]
            + L("# cartouche - mon nom + prénom")
            + [f"**{cv_data.get('nom', 'Lucas Tymen')}**"]
            + L("# cartouche - ville + code postal")
            + [ville_cp]
        )
        if final:
            lines.append(cv_data.get("telephone", ""))
            lines.append(cv_data.get("email", ""))
        else:
            lines += L("# cartouche - {{téléphone} - {email}}") + [f"{cv_data.get('telephone', '')} - {cv_data.get('email', '')}"]
        lines += L("# cartouche - ma landing page") + [landing, ""]
        lines += L("# sous titre - PROFIL") + ["PROFIL", cv_data.get("profil", ""), ""]
        lines += L("# sous titre - COMPETENCES PRINCIPALES") + ["COMPETENCES PRINCIPALES"]
        for cp in cv_data.get("competences_principales", []):
            lines += L("# compétence 1") + [f"**{cp.get('nom', '')}**"] + L("# articles (listé avec tirets)")
            for d in cp.get("details", []):
                lines.append(f"- {d}")
            lines.append("")
        lines += (
            L("# sous titre - OUTILS ET ENVIRONNEMENT")
            + ["OUTILS ET ENVIRONNEMENT"]
            + L("# articles - compressé sur 1 ligne, séparés par virgules")
            + [", ".join(str(x) for x in (cv_data.get("outils") or [])), ""]
        )
        for exp in cv_data.get("experiences", []):
            role = exp.get("role", "")
            entite = exp.get("entite", "")
            periode = exp.get("periode", "")
            lines += L("# sous titre - {EXPERIENCE} - {société} - {année}") + [f"**EXPERIENCE**", f"{role} - {entite} - {periode}"] + L("# articles (listé avec tirets)")
            for b in exp.get("bullets", []):
                lines.append(f"- {b}")
            lines.append("")
        lines += L("# sous titre - FORMATION") + ["**FORMATION**"]
        for f in cv_data.get("formation", []):
            etab = f.get("etablissement", "")
            niveau = f.get("niveau", "")
            intitule = f.get("intitule", "")
            annee = f.get("annee", "")
            if etab or niveau:
                lines += L("# {établissement} - {niveau}") + [f"*{etab}* - {niveau}"]
            if intitule or annee:
                lines += L("# {intitulé} - {année}") + [f"{intitule} - {annee}"]
            lines += L("# articles (listé avec tirets)")
            for d in f.get("details", []):
                lines.append(f"- {d}")
            lines.append("")
        soft_label = "ATOUTS" if final else "Softs skills"
        lines += L("# sous titre - Softs skills") + [soft_label] + L("# articles - compressé sur 1 ligne, séparés par virgules") + [", ".join(str(x) for x in (cv_data.get("soft_skills") or [])), ""]
        lines += L("# sous titre - LANGUES") + ["LANGUES"] + L("# articles (listé avec tirets)")
        for lg in cv_data.get("langues", []):
            lines.append(f"- {lg.get('langue', '')} : {lg.get('niveau', '')}")
        lines += [""] + L("# sous titre - DISPONIBILITE") + ["DISPONIBILITE"] + L("# articles - compressé sur 1 ligne, séparés par virgules") + [cv_data.get("disponibilite", "Paris, présentiel, Disponible"), ""]
        return "\n".join(lines)

    def _get_narratif_key(self, matching_data):
        secteur = matching_data.secteur_detecte
        if secteur == "it_support": return "it_support_pme"
        if "growth" in secteur or "seo" in secteur: return "accroche_growth"
        if secteur == "vente": return "accroche_vente"
        return "it_support_pme"

class LmCoordinator:
    def __init__(self, base_json: dict):
        self.base_json = base_json
        self.llm = OpenAIClient()

    def process(self, matching_data: MatchingOutput, offre: dict = None, contact_name: str = None) -> str:
        meta = self.base_json.get("meta", {})
        min_json_safe = _minify_json_safe(self.base_json)
        o = offre or {}
        entreprise = o.get("entreprise", "l'entreprise")
        titre_poste = o.get("titre") or matching_data.persona_selectionne
        reference = o.get("reference", "")
        ref_phrase = f" Référence annonce : {reference}." if reference else ""
        contact_phrase = f" (Destinataire connu : {contact_name} — tu peux personnaliser l'appel avec un ice-breaker discret.)" if contact_name else ""

        prompt = f"""
{ANTI_AI_PROMPT}
{REDACTION_DIRECTIVES}

MISSION :
Rédiger une lettre de motivation pour le poste « {titre_poste} » chez {entreprise}.{ref_phrase}
Citer la référence et l'intitulé du poste en début de corps de texte.
{contact_phrase}

Briques à utiliser (SANS en inventer — 0% hallucination) :
{min_json_safe}

Mots-clés de l'offre : {matching_data.mots_cles_ats}

CONSIGNES :
- Début par « Monsieur, Madame, » (ou personnalisé si destinataire connu). Aucune accroche du type « Bonjour », « J'espère que vous allez bien ».
- 1re partie : besoins de l'entreprise. 2e partie : solutions que j'apporte, argumentées (data-driven).
- Ton formel et chaleureux, dynamique, positif. Pas de listes à puces. Maximum 20-30 lignes.
- Signature : Lucas Tymen.
"""
        res = self.llm.chat_completion(prompt, system_prompt="Écrivain pro, tonalité anti-IA.", json_mode=False)
        return res.get("content", "Erreur.")

class EmailEngine:
    def __init__(self, base_json: dict):
        self.base_json = base_json
        self.llm = OpenAIClient()

    def process(self, matching_data: MatchingOutput, offre: dict = None, contact_name: str = None) -> dict:
        min_json_safe = _minify_json_safe(self.base_json)
        o = offre or {}
        titre_poste = o.get("titre") or matching_data.persona_selectionne
        reference = o.get("reference", "")
        contact_phrase = f" Personnaliser si destinataire connu ({contact_name})." if contact_name else ""

        prompt = f"""
{ANTI_AI_PROMPT}
{REDACTION_DIRECTIVES}

MISSION : Générer les emails J0, J2, J1, J1, J2 pour le poste « {titre_poste} ».{contact_phrase}
Citer la référence de l'annonce et l'intitulé du poste dans l'objet (sujet) et/ou en début du corps de chaque email.

Briques pro (SANS en inventer — 0% hallucination) :
{min_json_safe}

CONSIGNES pour chaque email :
- Formule « Monsieur, Madame, » (ou personnalisée). Aucune accroche « Bonjour », « J'espère que vous allez bien ».
- Ton formel et chaleureux, dynamique, positif, data-driven. Court (vingtaine à trentaine de lignes max).
- Sujet : inclure référence et/ou intitulé du poste.

OUTPUT JSON: {{ "email_j0": "...", "email_j2": "...", "email_j1": "...", "email_j1_bis": "...", "email_j2_bis": "...", "sujet": "..." }}
"""
        res = self.llm.chat_completion(prompt, system_prompt="Écrivain pro, tonalité anti-IA.", json_mode=True)
        if not isinstance(res, dict):
            res = {}
        fallback = {
            "email_j0": "", "email_j2": "", "email_j1": "", "email_j1_bis": "", "email_j2_bis": "",
            "sujet": f"Candidature - {o.get('titre', 'Poste')}"
        }
        return {**fallback, **(res or {})}
