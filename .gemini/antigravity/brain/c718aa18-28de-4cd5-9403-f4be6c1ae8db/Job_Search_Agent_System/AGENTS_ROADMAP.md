# Roadmap — Agents IA (Antigravity Bridge)

## Architecture & Coordination
- **Source de vérité :** `resources/base_real.json` (ou `cv_base_datas_pour_candidatures.json`, `base.json`). ATV Strict.
- **Coordination :** Triplet `AGENTS_LOG.md`, `AGENTS_ROADMAP.md`, `AGENTS_TODO.md`.
- **Historique :** `HISTORIQUE.md` — timestamps, pays (France), moments clés, benchmarks.
- **Architecture agentique :** `ARCHITECTURE_AGENTIQUE.md` — explication de l’approche agentic et rôle de chaque agent.
- **Sprint corrections :** `SPRINT_CORRECTIONS.md` — plan de sprint collectif (corrections audit, test réel, rapports par agent). Coordination : chef de projet + expert_automatisation.
- **LLM :** Groq (prioritaire) ou OpenAI `gpt-4o-mini` (via `core/llm_client.py`).

## Workflow Actuel
1. **Cron principal :** `--mode both` = scan + matching + filtre POSTULER + pipeline full (CV/LM/emails)
2. **Cron relances :** `followup_runner` — séquence **J0 → J2 → J1 → J1 → J2** (J+2, J+4, J+7, J+9) via Gmail drafts
3. **Découverte :** requêtes persona-driven (`persona_queries.py`)
4. **Matching :** déterministe Python (MatchingEngine), seuils POSTULER >= 60
5. **Telegram :** `/pipeline <url> [draft]` — accepte fiche d'offre ou **page de recherche** (Glassdoor, Indeed, WTTJ, etc.) : annonces extraites et traitées une par une. Chatbot langage naturel.
6. **Déploiement :** GitHub Actions (`.github/workflows/deploy.yml`) — push main → transfert tar + `contabo_safe_deploy.sh`. Secrets : `SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY`. Voir `scripts/DEPLOIEMENT_SAFE.md`.

## Rédaction (LM & Emails)
- **Directives partagées :** `REDACTION_DIRECTIVES` dans `agents/generator.py` — ton formel et chaleureux, **pas** « Bonjour / J'espère que vous allez bien », formule « Monsieur, Madame, » (personnalisable si recruteur connu), structure besoins entreprise → solutions argumentées, 20–30 lignes max, **0% hallucination**, référence + intitulé cités (corps ou objet). **Aucun placeholder** type `{{titre_poste}}` : utiliser les valeurs fournies ou omettre.
- **Sanitisation :** `core/utils.sanitize_placeholders()` — remplace ou supprime tout `{{...}}` avant envoi (sujet/corps brouillon). Si donnée manquante → chaîne vide, jamais laisser de placeholder.
- **LmCoordinator / EmailEngine :** acceptent `offre` (titre, entreprise, reference) et `contact_name` (personnalisation, ice-breaker).

## CV (Structure & Génération)
- **Structure markdown stricte :** titre poste, référence annonce, entreprise, cartouche (nom, ville, tél, email, landing), PROFIL, COMPETENCES PRINCIPALES, OUTILS, EXPERIENCE, FORMATION, ATOUTS, LANGUES, DISPONIBILITE. Mode **final** (`render_cv_markdown(..., final=True)`) : sans lignes `#`, tél/email sur 2 lignes, section ATOUTS.
- **Secteur it_support :** période 2000–2022 (periode_it), expériences filtrées (priorite_secteur principale/secondaire), compétences/ATOUTS depuis `competences_detaillees.it_support_systemes`, tri APSI en tête.
- **Charte pièces jointes :** `core/utils.attachment_filenames(entreprise, titre_poste)` → `CV_Lucas_Tymen_{société}_{intitulé}.pdf`, `LM_...`.

## Prochaines Étapes (Phase 3+)
- **PDF Engine :** `agents/cv_pdf.py` — génération à brancher sur le CV markdown ou sur `cv_data` avec noms de fichiers charte.
- **Attachments :** Orchestrator `create_draft=True` utilise déjà la charte de noms ; les PDF doivent être générés avec ces noms pour être joints.

## Règles de Développement
- **Principe Antigravity :** Ne jamais inventer de données non présentes dans le JSON de base.
- **Atomicité :** Chaque agent doit être testable isolément.
- **Documentation :** Mettre à jour `AGENTS_LOG.md` après chaque modification structurelle.
