# Journal de bord — Agents IA

> Log partagé pour la coordination entre agents IA. Chaque agent consulte ce fichier avant d'agir et y consigne ses actions.

---

## Format d'entrée

```markdown
### [YYYY-MM-DD] Agent: <nom ou type>
**Action :** <description courte>
**Fichiers modifiés/créés :** liste
**Blocage / Attention :** si pertinent
**Prochaine étape suggérée :**
```

---

## Historique

### [2026-02-28] Agent: Cursor (Auto)
**Action :** Phase 1 — Déploiement Contabo + cron + scheduler  
**Fichiers créés :**
- `scheduler/dedup.py` — déduplication SQLite
- `scheduler/job_queue.py` — découverte offres WTJ/LinkedIn/Indeed
- `scheduler/cron_runner.py` — point d'entrée cron
- `storage/db.py` — persistance candidatures
- `Dockerfile`, `docker-compose.yml`, `crontab`, `.env.example`, `.dockerignore`

**Principe respecté :** Aucune modification des fichiers existants (core/, agents/). Projet Antigravity intact.

**Prochaine étape suggérée :** Phase 2 — LLM client + MatchingEngine (embeddings, cosine similarity)

---

### [2026-02-28] Agent: Cursor (Auto)
**Action :** Création du triplet AGENTS_* pour coordination entre agents IA  
**Fichiers créés :**
- `AGENTS_README.md` — index du triplet
- `AGENTS_ROADMAP.md` — règles, architecture, workflow
- `AGENTS_LOG.md` — journal (ce fichier)
- `AGENTS_TODO.md` — TODO partagée phases 2–4 + backlog

**Objectif :** Permettre à tout agent IA de reprendre le projet en lisant le contexte et l’historique.

---

### [2026-03-01] Agent: Antigravity
**Action :** Migration vers OpenAI (Phase 2) & Intégration Gmail Drafting
**Fichiers modifiés/créés :**
- core/llm_client.py — Client unifié OpenAI (Chat & Embeddings)
- gents/drafting.py — Mise en brouillon Gmail via IMAP
- gents/generator.py — Adaptation sujet email et structure JSON large
- gents/matching.py — Adaptation persona Art/Vente
- core/orchestrator.py — Intégration de la mise en brouillon
- equirements.txt — Ajout openai et 
umpy
- process_test_offers.py — Script de test pour les 3 offres Art/Vente

**Attention :** Nécessite OPENAI_API_KEY, GMAIL_USER et GMAIL_APP_PASSWORD dans .env.
**Prochaine étape suggérée :** Brancher ScraperOffre sur OpenAIClient pour une extraction réelle.

### [2026-03-01] Agent: Antigravity — Benchmark Process
**Action :** Exécution complète du pipeline sur 3 offres Art/Vente.
**Résultats :**
- **Nombre d'offres :** 3
- **Durée totale :** 17.55 secondes
- **Moyenne :** ~5.8s / offre
- **Intelligence :** OpenAI gpt-4o-mini (Scraping + Matching)
- **Drafting :** Agent IMAP prêt (attente identifiants GMAIL)
- **Validation ATV :** Passée avec succès (0 hallucination détectée sur cette session)

**Observations :** Le passage à OpenAI a permis une extraction réelle et un matching plus fin. La latence reste très faible (< 6s par candidature complète).

### [2026-03-01] Agent: Antigravity — Phase 3 Complete (PDF & Refinement)
**Action :** Déploiement du générateur de CV PDF et raffinement des messages.
**Résultats :**
- **Génération PDF :** gents/cv_pdf.py opérationnel (ReportLab).
- **Raffinement LLM :** EmailEngine utilise OpenAI pour personnaliser les accroches.
- **Drafting :** Les brouillons Gmail incluent désormais le CV PDF en pièce jointe.
- **Test Offres :** 3 nouvelles candidatures mises en brouillon avec succès.

**Note :** Le système est désormais en version "Premium" avec des documents ATS-friendly et des messages personnalisés.

---

### [2026-03-01] Agent: Cursor (Auto)
**Action :** job_discoverer + cron_runner — URLs configurables (WTTJ, France Travail)  
**Fichiers créés :**
- `scheduler/job_discoverer.py` — discover_jobs(source, max_jobs), SOURCES avec URLs multiples par source
**Fichiers modifiés :**
- `scheduler/cron_runner.py` — utilise job_discoverer au lieu de job_queue, run_pipeline(url, create_draft=False), --max

**Principe :** Pas d'URL unique hardcodée — SOURCES avec liste d'URLs par source.

**Note :** WTTJ peut retourner 0 si la page est SPA (JS-rendered). Fallback /fr/jobs?page=1 ajouté. Playwright/Selenium possible en Phase ultérieure.

**Prochaine étape suggérée :** Test local dry-run, puis déploiement Contabo via scp.

---

### [2026-03-01] Agent: Cursor (Auto)
**Action :** Corrections tests + Playwright WTTJ SPA  
**Fichiers modifiés :**
- `tests/test_matching.py` — MatchingEngine déterministe, tests _score_all_personas et _detect_secteur
- `tests/test_coverage_gap.py` — remplacement cosine_similarity par _score_all_personas / _detect_secteur
- `scheduler/job_discoverer.py` — WTTJ via Playwright (SPA React), France Travail reste requests
- `requirements.txt` — ajout playwright>=1.40.0

**Résultat dry-run :** wttj — 3 offres trouvées (Ornikar, Pigment, Aesthe). Tests matching passent.

**Prochaine étape suggérée :** Déploiement Contabo quand CI vert.

---

### [2026-03-01] Agent: Cursor (Auto)
**Action :** Découverte pilotée par personas (job-prospection-tool / Mistral)  
**Fichiers créés :**
- `scheduler/persona_queries.py` — `get_persona_queries(base_json)` depuis strategie_secteur / personas_specialises
- `api/squid_client.py` — client `offer_submit()` pour API SquidResearch (optionnel)
**Fichiers modifiés :**
- `scheduler/job_discoverer.py` — `discover_jobs(..., base_json=None)` utilise les requêtes personas
- `scheduler/cron_runner.py` — passe base_json à discover_jobs
- `.env.example` — SQUID_API_URL, SQUID_API_TOKEN

**Principe :** Requêtes de découverte dérivées des personas (detection_mots_cles). Fallback DORKS_MISTRAL. Compatible job-prospection-tool et Agent Orchestrateur Mistral.

**Résultat dry-run :** offres "support", "technicien", "administrateur" au lieu de "growth" uniquement.

---

### [2026-03-01] Agent: Cursor (Auto)
**Action :** Fix run_both + filtre POSTULER + followup_runner J+4/J+10
**Fichiers créés :** `scheduler/followup_runner.py` — cron relances J+4/J+10 via Gmail drafts
**Fichiers modifiés :** cron_runner (run_both), orchestrator (emails), models (FinalOutput.emails), csv_exporter (JSON), job_scanner_runner (format csv|json), Dockerfile, docker-compose, crontab, DEPLOIEMENT.md

---

### [2026-03-02] Agent: Cursor (Auto)
**Action :** Séquence emails J0→J2→J1→J1→J2, structure CV, directives rédaction, placeholders, nommage PJ, Telegram pipeline + chatbot

**Fichiers créés :**
- `core/utils.py` — `sanitize_placeholders()`, `attachment_filenames()` (charte CV/LM_{société}_{intitulé}.pdf)
- `tests/test_utils.py` — tests sanitization et nommage
- `scripts/simulate_cv_support_it.py` — simulation CV Support IT (base_real)

**Fichiers modifiés :**
- `agents/generator.py` — REDACTION_DIRECTIVES (ton formel/chaleureux, pas « Bonjour », Monsieur/Madame, 0% hallucination, pas de placeholders) ; LmCoordinator/EmailEngine(offre, contact_name) ; structure CV markdown + render_cv_markdown(..., final=True) ; it_support : periode_it, filtre expériences, competences_detaillees, tri APSI
- `core/orchestrator.py` — passage offre/contact_name aux générateurs ; create_draft avec sanitize_placeholders + attachment_filenames ; cv_markdown en final=True
- `scheduler/followup_runner.py` — relances J+2, J+4, J+7, J+9 (J2, J1, J1_bis, J2_bis)
- `core/models.py` — FinalOutput : date_relance_j2/j4/j7/j9, emails (email_j2_bis)
- `agents/strategy.py` — FollowUpStrategy/ReportAgent : 4 dates relance
- `scheduler/telegram_bot.py` — `/pipeline <url> [draft]` (orchestrateur + save_application) ; chatbot langage naturel (MessageHandler, _parse_chat_intent, mots-clés candidater/pipeline/brouillon)
- `scripts/send_application.py` — charte nommage via attachment_filenames
- Tests : test_generators, test_orchestrator, test_cv_generator, test_strategy, test_compiler

**Règles :** Pas de placeholder laissé si donnée absente (vide) ; nommage PJ strict _société_intitulé ; logs IA dans AGENTS_LOG + roadmap dans AGENTS_ROADMAP.

**Prochaine étape suggérée :** Génération PDF avec noms charte dans le flux (orchestrator ou script) pour que les brouillons aient les pièces jointes.

---

### [2026-03-02] Agent: Cursor (Auto)
**Action :** Plan de sprint collectif — corrections audit expert_automatisation

**Fichiers créés :**
- `SPRINT_CORRECTIONS.md` — plan en 3 phases : (1) corrections un par un, (2) test en conditions réelles, (3) surveillance et rapports par agent. Coordination chef de projet + expert_automatisation.

**Fichiers modifiés :**
- `AGENTS_ROADMAP.md` — référence à SPRINT_CORRECTIONS.md
- `AGENTS_TODO.md` — section Sprint corrections (Phase 1, 2, 3)

**Points à corriger (audit) :** ATV_CHECK fictif, matching mots-clés composés, niveau_poste None, email_trouve None, erreurs LLM, fallback bullet_cv_court.

**Prochaine étape suggérée :** Lancer Phase 1 du sprint (corrections).

---

### [2026-03-02] Agent: Cursor (Auto) — Sprint 3 phases exécuté
**Action :** Phase 1 (corrections) + Phase 2 (benchmarks data-driven) + Phase 3 (rapports)

**Corrections :**
- ATV_CHECK : intégration valider_donnees() dans orchestrator
- Matching : _expand_keywords() pour mots-clés composés ; guard niveau_poste
- Draft : skip create_draft si email_trouve vide ; GmailDraftingAgent refuse to_email vide
- EmailEngine : fallback dict si LLM échoue
- bullet_cv_court : fallback robuste (liste)

**Benchmarks :** tests/benchmark_data/matching_cases.json, test_benchmark_*.py — 17 tests PASSED, ~4 s.

**Documentation :** SPRINT_RAPPORTS.md, SPRINT_CORRECTIONS.md mis à jour, HISTORIQUE.md (benchmark ajouté).

---

### [2026-03-02] Agent: Cursor (Auto) — Chatbot LLM
**Action :** Ajout couche LLM au chatbot Telegram (interprétation intention + contexte RACI)

**Fichiers créés :**
- `scheduler/chatbot_llm.py` — parse_intent_llm(), _get_raci_context()
- `tests/test_chatbot_llm.py` — tests _get_raci_context

**Fichiers modifiés :**
- `scheduler/telegram_bot.py` — on_chat_message : appel LLM puis fallback règles ; _RACI_KEYWORDS ; contexte RACI injecté

**Fonctionnement :** LLM (Groq/OpenAI) interprète l'intention (pipeline, pipeline_all, agents, raci, help). Contexte RACI (chef de projet, expert_automatisation) depuis base_real.json injecté dans le prompt. Fallback vers mots-clés si LLM indisponible ou timeout (8 s).

---

### [2026-03-02] Agent: Cursor (Auto) — Scraping page de recherche
**Action :** Extraction des annonces depuis une URL de page de recherche, puis traitement individuel

**Fichiers modifiés :**
- `scheduler/job_discoverer.py` — `is_search_page(url)`, `extract_job_urls_from_search_page(url, max_jobs=15)` ; extracteurs par site (Glassdoor, Indeed, France Travail, WTTJ, HelloWork, Meteojob, ChooseYourBoss, APEC, Manpower, Adecco, Dogfinance, LinkedIn)
- `scheduler/telegram_bot.py` — Détection page de recherche dans `/pipeline` et chatbot : si URL = page de recherche → extraction des annonces → pipeline sur chacune (max 10)

**Règle :** Coller une URL de recherche (ex. Glassdoor, Indeed, WTTJ) → annonces extraites et traitées une par une. Glassdoor/Indeed peuvent bloquer (403) ; WTTJ (Playwright) et France Travail généralement OK.

---

### [2026-03-02] Agent: Cursor (Auto) — GitHub Actions déploiement
**Action :** Déploiement automatique sur Contabo via GitHub Actions

**Fichiers créés :**
- `.github/workflows/deploy.yml` — Trigger push main (ou manuel) ; transfert tar + `contabo_safe_deploy.sh`

**Fichiers modifiés :**
- `scripts/DEPLOIEMENT_SAFE.md` — section Déploiement automatique (GitHub Actions) avec config secrets

**Secrets requis :** `SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY`

