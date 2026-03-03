# Mission DevOps + Expert Automatisation — Diagnostic et correctifs

**Date :** 2026-03-03  
**Constat utilisateur :** « Candidater sur tous les scans » affiche « traité » mais rien n’apparaît dans la boîte d’envoi. Rien ne bouge.

---

## Diagnostic (expert_automatisation)

### 1. Erreur 429 — Groq API rate limit

Les logs montrent : `HTTP/1.1 429 Too Many Requests` sur `api.groq.com`.

- **Impact :** Les appels LLM (extraction offre, génération LM/emails) échouent.
- **Conséquence :** Le scraper renvoie « Entreprise Inconnue, Poste Inconnu » pour toutes les offres.
- **Correctif :** Retry avec backoff + fallback automatique sur OpenAI si Groq renvoie 429.

### 2. Pipeline crée des BROUILLONS, pas des mails envoyés

Le système crée des **brouillons Gmail** (dossier Brouillons), pas des emails dans Envoyés.

- `create_draft=True` → écriture dans **Brouillons** (révision manuelle puis envoi).
- « Candidater sur tous les scans » utilise `create_draft=False` → **aucun brouillon** créé, uniquement enregistrement en base.

### 3. `pipeline_all` avec `create_draft=False`

- **Comportement actuel :** Traitement (extraction, matching, CV, LM) + sauvegarde dans `applications.db`. Aucun brouillon Gmail.
- **Limitation :** Même avec `create_draft=True`, l’`EntrepriseScraper` renvoie rarement un email → brouillons peu créés.

---

### 4. Limite artificielle à 5 offres (pipeline_all)

`_last_scan_job_urls(max_urls=5)` limitait à 5 offres, quel que soit le contenu du scan.

- **Impact :** Toujours 5 offres traitées, même si le scan en contient 20 ou 50.
- **Correctif :** `max_urls` porté à 30. Affichage `/offres` : 20 offres au lieu de 10.

---

## Correctifs assignés

| Agent | Tâche | Statut |
|-------|-------|--------|
| **Expert automatisation** | Retry + fallback OpenAI sur 429 dans `core/llm_client.py` | ✅ Implémenté |
| **Expert automatisation** | Vérifier robustesse extraction (fallback ScraperOutput sur erreur LLM) | ✅ Existant |
| **DevOps** | Documenter le flux (brouillons vs envoyés, limite rate limit Groq) | ✅ Doc |
| **Expert automatisation** | Corriger limite 5 → 30 dans _last_scan_job_urls et affichage /offres | ✅ Implémenté |
| **Pentester** | Audit sécurité : pas d’exposition des clés API en cas de 429/retry | — |

---

## Messages utilisateur à clarifier

- « Candidater sur tous » → Traitement + sauvegarde. Les brouillons Gmail ne sont créés que via `/pipeline <url> draft` (et si un email est trouvé).
- Les brouillons sont dans **Brouillons** Gmail, pas dans **Envoyés** — à relire et envoyer manuellement.
