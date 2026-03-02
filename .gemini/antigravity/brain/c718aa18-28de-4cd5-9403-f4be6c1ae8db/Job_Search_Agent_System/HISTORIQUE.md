# Historique du projet — Job Search Agent System

> Chronologie des moments clés, avec timestamps, périmètre géographique et résultats de benchmarks marquants.

---

## Format des entrées

| Champ | Description |
|-------|-------------|
| **Date** | Timestamp (YYYY-MM-DD) de l’événement |
| **Pays** | Périmètre principal (marché cible, déploiement, sources d’offres) |
| **Moment clé** | Résumé de l’étape ou de la décision |
| **Benchmarks / Résultats** | Chiffres mesurés ou observés (temps, volume, scores, qualité) |

---

## Chronologie

### 2026-02-28 — Lancement infrastructure

| Pays | Moment clé | Benchmarks / Résultats |
|------|------------|------------------------|
| **France** | Phase 1 — Déploiement Contabo, cron, scheduler | Création `dedup.py`, `job_queue.py`, `cron_runner.py`, `storage/db.py` ; Docker + crontab opérationnels. **Principe :** aucun changement dans `core/` et `agents/` (Antigravity intact). |

| Pays | Moment clé | Benchmarks / Résultats |
|------|------------|------------------------|
| **France** | Création du triplet AGENTS_* pour coordination multi-agents | Fichiers : `AGENTS_README.md`, `AGENTS_ROADMAP.md`, `AGENTS_LOG.md`, `AGENTS_TODO.md`. **Objectif :** tout agent IA peut reprendre le contexte et l’historique. |

---

### 2026-03-01 — LLM, matching et première chaîne complète

| Pays | Moment clé | Benchmarks / Résultats |
|------|------------|------------------------|
| **France** | Migration vers OpenAI (Phase 2) + intégration Gmail Drafting | `core/llm_client.py` (OpenAI), `agents/drafting.py` (IMAP), `agents/generator.py` (sujet email, JSON), `agents/matching.py` (personas Art/Vente). Dépendances : `OPENAI_API_KEY`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`. |

| Pays | Moment clé | Benchmarks / Résultats |
|------|------------|------------------------|
| **France** | **Benchmark Process — Pipeline complet sur 3 offres Art/Vente** | **Nombre d’offres :** 3 — **Durée totale :** **17,55 s** — **Moyenne :** **~5,8 s / offre** — LLM : OpenAI gpt-4o-mini (scraping + matching) — **Validation ATV :** 0 hallucination détectée sur la session. |

| Pays | Moment clé | Benchmarks / Résultats |
|------|------------|------------------------|
| **France** | Phase 3 — Générateur PDF + raffinement messages | `agents/cv_pdf.py` (ReportLab) ; EmailEngine personnalise les accroches ; brouillons Gmail avec CV PDF en pièce jointe. **Résultat :** 3 candidatures mises en brouillon avec succès. |

| Pays | Moment clé | Benchmarks / Résultats |
|------|------------|------------------------|
| **France** | Découverte d’offres — URLs configurables (WTTJ, France Travail) | `scheduler/job_discoverer.py` avec SOURCES multi-URLs ; cron utilise `discover_jobs`, `run_pipeline(url, create_draft=False)`. WTTJ SPA → fallback Playwright prévu. |

| Pays | Moment clé | Benchmarks / Résultats |
|------|------------|------------------------|
| **France** | Tests + Playwright pour WTTJ (SPA React) | MatchingEngine déterministe (tests `_score_all_personas`, `_detect_secteur`). **Dry-run :** **3 offres trouvées** (Ornikar, Pigment, Aesthe). Playwright ≥1.40.0 ajouté. |

| Pays | Moment clé | Benchmarks / Résultats |
|------|------------|------------------------|
| **France** | Découverte pilotée par personas (Mistral / job-prospection-tool) | `scheduler/persona_queries.py` : requêtes dérivées de `strategie_secteur` / `personas_specialises`. **Résultat dry-run :** offres « support », « technicien », « administrateur » (plus seulement « growth »). |

| Pays | Moment clé | Benchmarks / Résultats |
|------|------------|------------------------|
| **France** | run_both + filtre POSTULER + followup_runner | `scheduler/followup_runner.py` — relances J+4 / J+10 via brouillons Gmail ; cron `run_both` ; filtre sur `next_action == "POSTULER"`. |

---

### 2026-03-02 — Rédaction, CV, Telegram, séquence relances

| Pays | Moment clé | Benchmarks / Résultats |
|------|------------|------------------------|
| **France** | Séquence emails J0→J2→J1→J1→J2, structure CV, directives rédaction, Telegram | `core/utils.py` : `sanitize_placeholders()`, `attachment_filenames()` — charte `CV_` / `LM_` par société et intitulé. **Directives :** ton formel/chaleureux, 0 % hallucination, pas de placeholders résiduels. Relances J+2, J+4, J+7, J+9. **Telegram :** `/pipeline <url> [draft]` + chatbot langage naturel (candidater / pipeline / brouillon). |

---

## Synthèse des benchmarks les plus frappants

| Métrique | Valeur | Contexte |
|----------|--------|----------|
| **Temps moyen par candidature complète** | **~5,8 s** | 3 offres, extraction + matching + génération (OpenAI gpt-4o-mini). |
| **Durée totale pipeline (3 offres)** | **17,55 s** | Benchmark Process 2026-03-01. |
| **Hallucination (ATV)** | **0** | Session benchmark ; logique déterministe Python pour le matching. |
| **Offres découvertes (dry-run WTTJ)** | **3** | Ornikar, Pigment, Aesthe — découverte Playwright SPA. |
| **Seuils matching** | **≥60 POSTULER, ≥30 À surveiller** | Scoring déterministe par intersection de mots-clés (poids configurable). |
| **Relances automatisées** | **J+2, J+4, J+7, J+9** | 4 dates de relance via brouillons Gmail. |
| **Benchmark sprint corrections** | **16 tests, ~3 s** | Matching, ATV, régression (niveau_poste, composites, fallback). |

---

### 2026-03-02 — Scraping page de recherche + déploiement auto

| Pays | Moment clé | Benchmarks / Résultats |
|------|------------|------------------------|
| **France** | Scraping page de recherche (Glassdoor, Indeed, WTTJ, etc.) | `job_discoverer.py` : `is_search_page()`, `extract_job_urls_from_search_page()`. Coller une URL de recherche → annonces extraites et traitées individuellement (max 10). Intégré dans `/pipeline` et chatbot Telegram. |
| **France** | Déploiement automatique GitHub Actions | `.github/workflows/deploy.yml` — push sur `main` → transfert tar + `contabo_safe_deploy.sh`. Secrets : `SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY`. |

---

## Périmètre géographique

- **Pays principal :** **France** (sources WTTJ, France Travail ; rédaction en français ; déploiement Contabo).
- Les personas et la base de profil (`base_real.json`) sont pensés pour le marché français (ESN, PME, intérim, SaaS).

---

*Dernière mise à jour : 2026-03-02. Pour le détail des actions par agent, voir `AGENTS_LOG.md`. Pour la procédure de déploiement (manuelle et automatique), voir `scripts/DEPLOIEMENT_SAFE.md`.*
