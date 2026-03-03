# Rapport commun — Analyse des interactions et processus

**Objectif** : Candidater partout, envoyer les emails (brouillons), lancer la séquence de relances pour toutes les URLs, et documenter les blocages pour corriger et améliorer l’outil.

---

## 1. Ce qui a été mis en place

### 1.1 Script batch (automatisation complète)

- **Fichier** : `scripts/batch_apply_urls.py`
- **Rôle** : Pour chaque URL fournie :
  1. Lancer le pipeline (extraction → matching → génération CV/LM/emails)
  2. Créer le brouillon Gmail (J0) si `email_trouve` est renseigné
  3. Enregistrer la candidature en base (`save_application`) pour que la séquence de relances (J+2, J+4, J+7, J+9) soit prise en charge par `followup_runner`

**Usage** :
```bash
# Toutes les URLs dans urls_batch.txt (déjà rempli avec ta liste)
python scripts/batch_apply_urls.py

# Fichier personnalisé
python scripts/batch_apply_urls.py --file mes_urls.txt

# Sans créer les brouillons (uniquement pipeline + enregistrement)
python scripts/batch_apply_urls.py --no-draft

# Limiter à 5 URLs pour test
python scripts/batch_apply_urls.py --max 5

# Simuler (affiche les URLs sans exécuter)
python scripts/batch_apply_urls.py --dry-run
```

**Relances** (à lancer après le batch, ou en cron quotidien) :
```bash
python -m scheduler.followup_runner        # crée les brouillons J+2, J+4, J+7, J+9
python -m scheduler.followup_runner --dry-run   # simule
```

### 1.2 Fichier d’URLs

- **Fichier** : `urls_batch.txt` (à la racine du projet)
- Contient toutes les URLs fournies (Lever, Ashby, Welcome to the Jungle), une par ligne. Les lignes commençant par `#` sont ignorées.

---

## 2. Problèmes identifiés (pourquoi « ça plante » ou s’arrête vite)

### 2.1 Telegram : liste d’URLs

- **Comportement actuel** : En langage naturel ou via le chatbot, une seule URL est utilisée (`_parse_chat_intent` retourne `urls[0]`). Si tu colles 50 URLs, seule la première est traitée.
- **« Pipeline toutes »** : Utilise les offres du **dernier scan** (`_last_scan_job_urls`, max 30), pas la liste collée dans le message. Donc coller une liste d’URLs ne déclenche pas le traitement de cette liste.
- **Limites** :
  - Rate limit : 10 requêtes / 60 s → au-delà, « Rate limit atteint ».
  - Page de recherche : max 10 annonces extraites par page.
  - Un message par offre traitée → risque de flood et lenteur sur 30 URLs.

**Conclusion** : Depuis Telegram, une **longue liste d’URLs** n’est pas supportée ; le flux est conçu pour une URL ou pour les offres du dernier scan. D’où l’impression que « même la liste seule des URLs plante » ou que ça s’arrête très vite.

### 2.2 Brouillons (emails) rarement créés

- **Cause** : `EntrepriseScraper` est un **stub** qui retourne toujours `email_trouve: None` (`agents/scraper.py`).
- **Conséquence** : Dans `orchestrator.py`, le brouillon J0 n’est créé que si `email_dest` est non vide. Donc en l’état, **aucun brouillon J0** n’est créé (sauf si un autre mécanisme injecte un email).
- **Relances** : `followup_runner` ne crée des brouillons de relance que pour les candidatures qui ont un `contact_cible` / `email_trouve` en base. Si tout est « Inconnu », aucune relance par email n’est créée.

**À faire** : Enrichir `EntrepriseScraper` (scraping page carrière, API, ou fallback type `recrutement@domaine.com`) pour avoir un email quand c’est possible.

### 2.3 Support des plateformes (Lever, Ashby, WTTJ)

- **Welcome to the Jungle** : Support explicite (page de recherche + fiches directes) dans `job_discoverer` et scraper.
- **Lever** et **Ashby** : Fiches directes OK si l’URL est passée au pipeline (ex. via le script batch). En revanche, **aucune extraction depuis une page de recherche** Lever/Ashby dans `job_discoverer` (pas de branche dédiée). Donc pas de « /pipeline url_recherche_lever » qui extrait plusieurs fiches.

### 2.4 Timeouts et robustesse

- **WTTJ (Playwright)** : timeout 25 s dans `_extract_from_page_wttj` ; échec possible si la page est lente ou bloquée.
- **Chatbot LLM** : timeout 8 s pour l’intent → fallback règles si dépassement.
- **Scraper** : `requests.get(url, timeout=20)` ; sites anti-bot ou lents peuvent faire échouer l’extraction.

### 2.5 Cron / pipeline

- **cron_runner** : Utilise `discover_jobs()` (sources WTTJ, France Travail, etc.) puis pipeline sur les URLs découvertes. Pas d’entrée « liste d’URLs en fichier » ; le batch script comble ce manque.

---

## 3. Synthèse des corrections et améliorations à apporter

| Priorité | Problème | Correction / amélioration |
|----------|----------|----------------------------|
| **Haute** | Impossible d’utiliser une longue liste d’URLs depuis Telegram | **Fait** : script `batch_apply_urls.py` + `urls_batch.txt`. Depuis Telegram : proposer une commande du type `/batch` qui lit un fichier déposé ou une liste en pièce jointe (à spécifier). |
| **Haute** | Aucun brouillon créé (email_trouve toujours vide) | Enrichir `EntrepriseScraper` : détection email sur page carrière, ou fallback `recrutement@<domaine>` / champ configurable par offre. |
| **Moyenne** | Relances sans email | Même cause que ci‑dessus ; une fois `contact_cible` / `email_trouve` renseignés en base, les relances créeront les brouillons. |
| **Moyenne** | Lever / Ashby : pas d’extraction depuis page de recherche | Ajouter dans `job_discoverer` la détection et l’extraction des URLs d’offres pour les pages Lever et Ashby (si besoin). |
| **Basse** | Rate limit Telegram sur gros batches | Pour les gros volumes, utiliser le script batch en CLI plutôt que Telegram ; ou augmenter `RATE_LIMIT` / fenêtre, ou étaler les réponses (résumé groupé au lieu d’un message par offre). |
| **Basse** | Timeouts WTTJ / LLM | Ajuster les timeouts (ex. 30–40 s pour Playwright, 12 s pour LLM) ou ajouter retry avec backoff. |

---

## 4. Workflow recommandé pour « candidater partout + emails + relances »

1. **Préparer les URLs** dans `urls_batch.txt` (ou un fichier dédié).
2. **Lancer le batch** :
   ```bash
   python scripts/batch_apply_urls.py
   ```
3. **Consulter le rapport** dans `reports/batch_report_<timestamp>.md` (et `.json`) : OK / échecs / brouillons créés.
4. **Lancer les relances** (quotidien ou après le batch) :
   ```bash
   python -m scheduler.followup_runner
   ```
5. Les **brouillons** (J0 et relances) sont créés dans Gmail ; l’envoi reste manuel sauf intégration envoi automatique ultérieure.

---

## 5. Fichiers modifiés / ajoutés

- **Ajout** : `scripts/batch_apply_urls.py` — script batch candidature + brouillon + enregistrement.
- **Ajout** : `urls_batch.txt` — liste des URLs fournies.
- **Ajout** : `reports/RAPPORT_AMELIORATIONS.md` — ce rapport.
- Les rapports d’exécution du batch sont écrits dans `reports/batch_report_<timestamp>.json` et `.md`.

Ce rapport sert de base commune pour corriger et améliorer l’outil (Telegram, EntrepriseScraper, Lever/Ashby, timeouts, rate limit).
