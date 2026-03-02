# Architecture agentique — Job Search Agent System

> Explication de l’approche « agentic » et du rôle de chaque agent dans le pipeline.

---

## 1. Ce que « agentic » signifie ici

Dans ce projet, **agentic** désigne une architecture où **plusieurs agents spécialisés** travaillent en séquence, chacun avec **une responsabilité unique**, sous la coordination d’un **orchestrateur**. Ce n’est pas un seul LLM qui fait tout : les tâches sont réparties entre des composants déterministes (Python) et des appels LLM ciblés, avec une **source de vérité stricte** (le JSON de profil) pour éviter les hallucinations.

### Principes

| Principe | Description |
|----------|-------------|
| **Un agent = une mission** | Chaque agent a un rôle précis (extraire l’offre, matcher le profil, générer le CV, etc.). |
| **Orchestration centralisée** | L’orchestrateur enchaîne les étapes, passe les sorties d’un agent en entrée au suivant, et produit un résultat final structuré. |
| **Hybride LLM / déterministe** | L’extraction et la rédaction utilisent le LLM ; le matching et la structure du CV sont en Python déterministe pour la reproductibilité et le contrôle. |
| **ATV (Anti-Hallucination Vérifiable)** | Aucune donnée inventée : tout ce qui est généré (CV, LM, emails) s’appuie sur `base_real.json` et les sorties des étapes précédentes. |
| **Testabilité** | Chaque agent peut être testé isolément (entrée/sortie définies, modèles Pydantic). |

### Flux de données (résumé)

```
URL offre → ScraperOffre → MatchingEngine → (CvAtvGenerator, LmCoordinator, EmailEngine)
                ↓                    ↓                          ↓
         ScraperOutput        MatchingOutput              documents (CV, LM, emails)
                                                                  ↓
         EntrepriseScraper → email/contact → GmailDraftingAgent (brouillon) + CvPdfGenerator (PDF)
```

L’**orchestrateur** (`core/orchestrator.py`) exécute ce pipeline et assemble le `FinalOutput`.

---

## 2. Rôle de l’orchestrateur

- **Fichier :** `core/orchestrator.py` — classe `Orchestrator`.
- **Rôle :** Point d’entrée unique du pipeline « une URL → candidature prête ».
- **Actions :**
  1. Appeler `ScraperOffre` pour extraire les données de l’offre.
  2. Passer le résultat au `MatchingEngine` (déterministe).
  3. Appeler `EntrepriseScraper` pour contact/email entreprise.
  4. Lancer les générateurs (CV, LM, emails) avec le matching et l’offre.
  5. Assembler le `FinalOutput` (documents, canal, dates de relance, ATV_CHECK).
  6. Optionnel : générer les PDF (CvPdfGenerator) et créer le brouillon Gmail (GmailDraftingAgent).

L’orchestrateur ne contient pas de logique métier : il délègue tout aux agents et fait circuler les données.

---

## 3. Rôle de chaque agent

### 3.1 Extraction et découverte

| Agent | Fichier | Type | Rôle | Entrées | Sorties |
|-------|---------|------|------|--------|--------|
| **ScraperOffre** | `agents/scraper.py` | LLM + HTTP | Extraire de l’URL d’offre les champs structurés (titre, entreprise, mots-clés, niveau, problème métier). | URL | `ScraperOutput` (Pydantic) |
| **EntrepriseScraper** | `agents/scraper.py` | Déterministe (stub) | Récupérer infos entreprise (email, contact). Pour l’instant retourne un dictionnaire minimal ; à enrichir (scraping ou API). | URL | `dict` (email_trouve, contact_name, etc.) |

### 3.2 Matching et décision

| Agent | Fichier | Type | Rôle | Entrées | Sorties |
|-------|---------|------|------|--------|--------|
| **MatchingEngine** | `agents/matching.py` | **Déterministe** | Comparer les mots-clés de l’offre aux personas du profil (`base_json`), scorer chaque persona, choisir le meilleur et décider : POSTULER (score ≥60), À surveiller (≥30), PASSER. | `ScraperOutput`, `base_json` | `MatchingOutput` (persona, score, next_action, arguments_actives, mots_cles_ats) |

Aucun LLM dans le matching : reproductibilité et coût maîtrisé.

### 3.3 Génération de documents (rédaction)

| Agent | Fichier | Type | Rôle | Entrées | Sorties |
|-------|---------|------|------|--------|--------|
| **CvAtvGenerator** | `agents/generator.py` | Déterministe + structure | Construire la structure du CV (données + markdown) à partir du `base_json` et du matching (secteur, persona). Filtrage des expériences par secteur (ex. it_support). | `MatchingOutput`, offre (dict), `base_json` | `dict` (cv_data) + `render_cv_markdown()` → texte markdown |
| **LmCoordinator** | `agents/generator.py` | LLM | Générer la lettre de motivation en respectant les `REDACTION_DIRECTIVES` (ton, longueur, pas de placeholders, 0 hallucination). | `MatchingOutput`, offre, contact_name, `base_json` (anonymisé) | Texte LM |
| **EmailEngine** | `agents/generator.py` | LLM | Générer les emails (J0, J2, J4, J7, J9) et le sujet, personnalisés selon l’offre et le contact. | Idem LmCoordinator | `dict` (sujet, email_j0, email_j2, …) |

Les trois s’appuient sur les mêmes directives de rédaction et sur le profil pour rester cohérents et sans invention de faits.

### 3.4 Mise en forme et livraison

| Agent | Fichier | Type | Rôle | Entrées | Sorties |
|-------|---------|------|------|--------|--------|
| **CvPdfGenerator** | `agents/cv_pdf.py` | Déterministe | Produire les PDF du CV et de la LM à partir du markdown/texte, avec les noms de fichiers selon la charte (société, intitulé). | Nom de fichier, données CV ou texte LM | Chemin(s) des fichiers PDF |
| **GmailDraftingAgent** | `agents/drafting.py` | Déterministe (IMAP) | Créer un brouillon Gmail avec sujet, corps et pièces jointes (CV + LM PDF). | Email destinataire, sujet, corps, liste de chemins de fichiers | Succès/échec (brouillon créé ou non) |

### 3.5 Stratégie et rapport (support)

| Agent | Fichier | Type | Rôle | Entrées | Sorties |
|-------|---------|------|------|--------|--------|
| **FollowUpStrategy** | `agents/strategy.py` | Déterministe | Calculer les dates de relance (J+2, J+4, J+7, J+9) à partir de la date de candidature. | Date d’envoi | `dict` (date_relance_j2, j4, j7, j9) |
| **ReportAgent** | `agents/strategy.py` | Déterministe | Assembler les briques (offre, matching, documents, canal, email, relances) en un `FinalOutput` conforme au schéma Pydantic. | Offre, matching, documents, canal, email_trouve, follow_up | `FinalOutput` |
| **CanalApplication** | `agents/strategy.py` | Déterministe | Déduire le canal d’envoi (email direct vs formulaire/LinkedIn) selon la présence d’un email trouvé. | `email_trouve` | `dict` (canal_recommande, contact_cible) |

En pratique, l’orchestrateur utilise directement les sorties des agents principaux et recalcule les dates de relance ; ces composants de stratégie formalisent la logique réutilisable.

---

## 4. Composants « agents » côté scheduler et interface

En dehors du pipeline une-URL, d’autres composants jouent un rôle de type « agent » (tâche bien délimitée) :

| Composant | Fichier | Rôle |
|-----------|---------|------|
| **job_discoverer** | `scheduler/job_discoverer.py` | Découverte d’offres (WTTJ, France Travail, etc.) via Playwright/requests ; requêtes personas ; page de recherche : `is_search_page()`, `extract_job_urls_from_search_page()` — coller URL recherche → annonces extraites et traitées une par une. |
| **DedupStore** | `scheduler/dedup.py` | Éviter de retraiter les mêmes URLs (SQLite). |
| **followup_runner** | `scheduler/followup_runner.py` | Cron des relances : génération des brouillons J+2, J+4, J+7, J+9. |
| **Telegram bot** | `scheduler/telegram_bot.py` | Interface : `/pipeline <url> [draft]` (accepte fiche d'offre ou page de recherche), `/scan`, `/status`, chatbot. Si URL = page de recherche → extraction puis pipeline sur chaque annonce. |
| **chatbot_llm** | `scheduler/chatbot_llm.py` | Couche LLM : interprétation d'intention (pipeline, raci, agents, help) + contexte RACI injecté (chef de projet, expert_automatisation). Fallback règles si LLM indisponible. |

Ils ne sont pas des « agents » au sens Pydantic (entrée/sortie uniques), mais ils étendent le système de façon modulaire et pilotable.

---

## 5. Résumé visuel des rôles

```
[ URL ] → ScraperOffre (LLM) → ScraperOutput
                    ↓
         MatchingEngine (Python) → MatchingOutput  →  CvAtvGenerator → cv_data / markdown
                    ↓                                        →  LmCoordinator → LM
         EntrepriseScraper → contact/email                   →  EmailEngine → emails
                    ↓
         CvPdfGenerator → PDF CV + LM
                    ↓
         GmailDraftingAgent → brouillon Gmail

         Orchestrator assemble tout en FinalOutput (documents, dates relance, ATV_CHECK).
```

---

*Pour la chronologie et les benchmarks, voir `HISTORIQUE.md`. Pour les règles de coordination et le workflow, voir `AGENTS_ROADMAP.md`.*
