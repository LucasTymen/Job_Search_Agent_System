# Relance prospection (bonnes données + séquence de relance)

## Contexte
- Les brouillons ont été effacés (hallucinations). La base de connaissance a été corrigée (`resources/base_real.json`, `resources/cv_base_datas_pour_candidatures.json`).
- Pour chaque candidature enregistrée, une **séquence de relance** est créée automatiquement (J0 → J+2 → J+4 → J+7 → J+9).

## 1. Lancer la prospection (brouillons J0 + enregistrement)

Utilise la base corrigée (priorité : `base_real.json`, puis `cv_base_datas_pour_candidatures.json`).

```bash
# Depuis la racine du projet
python scripts/batch_apply_urls.py --file urls_opportunites.txt
# ou avec une autre liste
python scripts/batch_apply_urls.py --file urls_batch.txt
# optionnel : limiter le nombre d’URLs
python scripts/batch_apply_urls.py --file urls_batch.txt --max 5
# sans créer de brouillons (test)
python scripts/batch_apply_urls.py --file urls_opportunites.txt --no-draft --dry-run
```

Pour chaque URL :
- Extraction offre → matching → génération CV/LM/emails (J0, J2, J1, J1_bis, J2_bis)
- Si POSTULER et email trouvé : **un brouillon Gmail J0** (CV + LM) est créé ; tu l'envoies quand tu veux
- **Enregistrement en base** : `storage/applications.db` avec `result_json` (toute la séquence pour envoi auto)
- **Plusieurs adresses** : si tu indiques plusieurs contacts (fichier `url	email1, email2` ou override), la première est en **To**, les autres en **Cc** (brouillon J0 et relances).

## 2. Relances automatiques (tu n'as rien à faire après J0)

**Lors du batch** : les agents créent d’un coup tous les brouillons (J0 + J+2, J+4, J+7, J+9). Désormais : un brouillon J0 ; les relances sont envoyées par `followup_runner`.

Chaque ligne en base a :
- `status` : J0 → après envoi de ton brouillon J0 → relance_j2 → relance_j1 → relance_j1_bis → relance_j2_bis
- `result_json` : contient `emails` (email_j0, email_j2, email_j1, email_j1_bis, email_j2_bis, sujet)

```bash
# Envoi automatique des relances (par défaut)
python -m scheduler.followup_runner

# Simuler sans envoyer
python -m scheduler.followup_runner --dry-run

# Brouillons au lieu d'envoyer
python -m scheduler.followup_runner --draft
```

- **J+2** : envoi auto email_j2 → status relance_j2
- **J+4** : envoi auto email_j1 → relance_j1
- **J+7** : envoi auto email_j1_bis → relance_j1_bis
- **J+9** : envoi auto email_j2_bis → relance_j2_bis  

## 3. Points d’attention

- **Groq** : en cas de rate limit (429), le client fait fallback OpenAI si configuré. Attendre ~24 min ou passer en Dev Tier.
- **URLs mortes** : certaines URLs (ex. Lever 404) échouent au scraping ; le batch continue, les candidatures « Poste Inconnu » sont enregistrées en PASSER. Mieux vaut une liste d’URLs à jour (ex. `urls_opportunites.txt` ou `urls_batch.txt`).
- **Rapports** : après le batch, voir `reports/batch_report_YYYYMMDD_HHMMSS.json` et `.md`.

## 4. Résumé

| Action | Commande |
|--------|----------|
| **Lancer la campagne** (brouillon J0 + enregistrement) | `python scripts/batch_apply_urls.py --file urls_opportunites.txt` |
| **Envoi auto des relances** (à lancer chaque jour, ex. cron 8h) | `python -m scheduler.followup_runner` |
| Simuler (sans envoyer) | `python -m scheduler.followup_runner --dry-run` |
| Brouillons au lieu d’envoi | `python -m scheduler.followup_runner --draft` |

La séquence de relance est **créée pour chacun** dès l’enregistrement en base ; il suffit d’exécuter `followup_runner` aux dates voulues (cron ou manuel).
