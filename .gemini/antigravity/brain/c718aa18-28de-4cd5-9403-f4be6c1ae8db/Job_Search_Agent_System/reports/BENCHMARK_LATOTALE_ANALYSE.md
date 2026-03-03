# Benchmark /latotale — Test en conditions réelles

**Date** : 2026-03-03  
**Scope** : 56 URLs (Lever, Ashby, Welcome to the Jungle) — équivalent `/latotale` via `scripts/batch_apply_urls.py --file benchmark_urls.txt`  
**Fichier d’entrée** : `benchmark_urls.txt`

---

## 1. Contexte du test

- **Objectif** : Valider la séquence complète par URL (analyse → scraping → traitement → candidature multicanale email + enregistrement pour relances).
- **Commande exécutée** : `python scripts/batch_apply_urls.py --file benchmark_urls.txt`
- **Répartition des URLs** :
  - **Lever** : 7 (mistral x4, partoo, skyslope, alice-bob)
  - **Ashby** : 9 (silver, zapier, ramp x2, langfuse, Mintlify, whatnot, leland, readme)
  - **Welcome to the Jungle** : 40

Le run a été lancé avec un timeout long ; l’analyse ci‑dessous repose sur les **premiers résultats observés** (logs terminal) et sur les **comportements récurrents**.

---

## 2. Résultats observés (échantillon)

| # | Plateforme | URL (résumé) | Résultat | Temps | Détail |
|---|------------|--------------|----------|-------|--------|
| 1 | Lever | mistral/... Backend | OK — POSTULER | ~62 s | Brouillon indiqué (voir §4.1) |
| 2 | Lever | mistral/... Security | OK — POSTULER | ~67 s | Idem |
| 3 | Lever | partoo/... | OK — PASSER | ~57 s | **502 Bad Gateway** → contenu inaccessible, matching score 0 |
| 4 | Lever | mistral/... AI Deployment | OK — POSTULER | ~64 s | Brouillon indiqué |
| 5 | Lever | mistral/... Data | OK — À surveiller | ~51 s | Score 45 |
| 6 | Lever | skyslope/... | OK — À surveiller | ~55 s | Customer Support Technician |
| 7 | Lever | alice-bob/... | OK — PASSER | ~39 s | **404 Not Found** + erreur validation LLM (ScraperOutput) → fallback Poste Inconnu |
| 8 | Ashby | silver/... | En cours | — | AI Backend Engineer, fallback OpenAI après 429 |

**Métriques dérivées (sur l’échantillon)** :
- **Temps moyen par URL** : ~53 s (avec retries Groq puis fallback OpenAI).
- **Taux de succès pipeline** : 7/7 terminés sans crash (échecs HTTP gérés en fallback).
- **Brouillons** : Voir §4.1 (correction appliquée sur le décompte).

---

## 3. Problèmes identifiés

### 3.1 Groq — Rate limit 429 (TPD)

- **Symptôme** : `Rate limit reached for model llama-3.3-70b-versatile` — limite **100 000 tokens/jour** (TPD) atteinte dès le début du batch.
- **Effet** : Chaque appel LLM fait 2 retries (2 s, 4 s) puis **fallback OpenAI** → latence et coût OpenAI.
- **Impact** : Sur 56 URLs (~4 appels LLM par URL), le batch dépasse largement le TPD Groq ; tout le run repose sur OpenAI après les premières URLs.

**Actions recommandées** :
- Passer en **Dev Tier** Groq (ou autre tier avec TPD plus élevé) pour les gros batches.
- Ou **réduire la taille des prompts / le nombre d’appels** (cache, modèle plus petit pour extraction).
- Ou **prévoir un mode “OpenAI first”** pour les runs > N URLs.

### 3.2 Scraping — Erreurs HTTP (502, 404)

- **502 Bad Gateway** (Partoo) : La page Lever renvoie 502 ; le pipeline continue avec “Contenu inaccessible” → offre Non spécifié / score 0 / PASSER.
- **404 Not Found** (Alice-Bob) : Offre supprimée ou URL incorrecte. Le LLM renvoie un JSON d’erreur `{erreur: "Contenu inaccessible..."}` au lieu d’un `ScraperOutput` → **validation Pydantic échoue** ; le code a un fallback qui renvoie “Poste Inconnu / Entreprise Inconnue” et le pipeline continue.

**Actions recommandées** :
- Pour **502/5xx** : retry avec backoff (ex. 1, 2, 4 s) avant de considérer “contenu inaccessible”.
- Pour **404** : détecter 404 en amont et **ne pas appeler le LLM** ; remplir directement un `ScraperOutput` “offre indisponible” pour éviter l’erreur de validation.
- Optionnel : marquer en base les URLs en échec (502/404) pour ne pas les retraiter en boucle.

### 3.3 Validation LLM — ScraperOutput

- Quand le contenu est inaccessible, le LLM peut renvoyer un objet `{erreur: "..."}` au lieu des champs attendus (`titre`, `entreprise`, etc.) → **6 validation errors for ScraperOutput**.
- Le **fallback** dans `extract_with_llm` (retour d’un `ScraperOutput` par défaut) n’est pas pris si l’exception est levée avant (par ex. dans le parsing JSON → Pydantic).

**Actions recommandées** :
- En cas d’exception de validation sur la réponse LLM, **utiliser systématiquement** le `ScraperOutput` par défaut (Poste Inconnu, Entreprise Inconnue, etc.) au lieu de laisser remonter l’exception.
- Ou exiger un schéma JSON strict côté LLM (réponse toujours avec les champs requis).

### 3.4 Brouillons (draft) — Décompte et réalité

- **EntrepriseScraper** renvoie toujours `email_trouve: None`. L’orchestrateur ne crée donc **aucun brouillon Gmail** (condition `email_dest` non vide).
- Dans le rapport batch, `email_trouve` est sérialisé en `{"email_trouve": "None"}` (chaîne). Le script batch considérait la chaîne `"None"` comme un email valide → **draft_created True à tort**.
- **Correction faite** : le script batch traite maintenant `"None"`, `"inconnu"`, `"n/a"` comme absence d’email ; le décompte de brouillons créés est correct.

**Actions recommandées** :
- Enrichir **EntrepriseScraper** (email sur page carrière, API, ou fallback `recrutement@domaine`) pour avoir de vrais brouillons.
- Côté sérialisation : éviter de stocker `str(None)` pour `email_trouve` ; garder `null` ou clé absente.

---

## 4. Synthèse des actions

| Priorité | Problème | Action |
|----------|----------|--------|
| Haute | Groq TPD 100k dépassé en batch | Dev Tier Groq ou mode OpenAI-first pour N URLs > 10–15 |
| Haute | Aucun brouillon réel (email_trouve vide) | Enrichir EntrepriseScraper |
| Moyenne | 404 → validation ScraperOutput | Détecter 404 avant LLM ; ScraperOutput “offre indisponible” |
| Moyenne | 502/5xx | Retry avec backoff sur le scraping |
| Basse | Réponse LLM invalide (objet erreur) | Fallback ScraperOutput par défaut en catch validation |

---

## 5. Relances et suivi

- Toutes les candidatures **enregistrées** (OK avec `save_application`) sont éligibles à la séquence de relances **J+2, J+4, J+7, J+9**.
- Les relances ne créent des brouillons que si un **contact/email** est présent en base (`contact_cible` / `email_trouve`). Aujourd’hui, avec `email_trouve` vide, aucune relance email n’est créée.
- Commande pour lancer les relances : `python -m scheduler.followup_runner` (ou `--dry-run`).

---

## 6. Fichiers utiles

- **Rapport batch (généré à la fin du run)** : `reports/batch_report_<timestamp>.json` et `.md`
- **URLs du benchmark** : `benchmark_urls.txt`
- **Script** : `scripts/batch_apply_urls.py` (chrono et décompte brouillons corrigé)

Une fois le run complet terminé, ouvrir le dernier `batch_report_*.md` pour le détail par URL (OK/échec, temps, brouillon) et ajuster les actions ci‑dessus si besoin.
