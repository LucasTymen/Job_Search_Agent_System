# Directives agents — à appliquer et propager

> **À l’orchestrateur et au chef de projet :** prenez connaissance de ce document en priorité. Appliquez les directives qui s’imposent selon les cas et **informez les autres agents** (génération, matching, drafting, followup, Telegram, etc.) pour que les règles soient respectées partout.

---

## 1. Qui doit lire et propager

| Rôle | Fichier / périmètre | Action |
|------|---------------------|--------|
| **Orchestrateur** | `core/orchestrator.py` | Appliquer les règles contacts (To/Cc), brouillon J0 seul, canal_application.contact_cible + contact_cc. S’assurer que les générateurs reçoivent les bonnes données (base 2015–2022). |
| **Chef de projet** | Coordination (sprints, RACI, `SPRINT_CORRECTIONS.md`) | Prioriser les tâches, faire appliquer les directives par les bons agents, mettre à jour `AGENTS_LOG.md` et `AGENTS_ROADMAP.md` après changements structurels. |

Les autres agents (MatchingEngine, CvAtvGenerator, LmCoordinator, EmailEngine, GmailDraftingAgent, followup_runner, Telegram) doivent recevoir les consignes via le code et la doc mis à jour par l’orchestrateur et le chef de projet.

---

## 2. Directives en vigueur

### 2.1 Relances : envoi automatique (plus de brouillons à envoyer à la main)

- **Utilisateur** : envoie uniquement le **brouillon J0** (candidature avec CV + LM). Il n’a rien à faire pour J+2, J+4, J+7, J+9.
- **Système** : `scheduler/followup_runner.py` **envoie** les relances par SMTP (par défaut). Cron quotidien (ex. 8h) déclenche l’envoi aux bons jours.
- **Orchestrateur** : ne crée **que le brouillon J0** en batch (plus les 4 brouillons de relance).
- **Drafting** : `agents/drafting.py` — `send_email()` utilisé par followup_runner ; `create_draft()` pour J0 uniquement côté orchestrateur.
- **Option** : `python -m scheduler.followup_runner --draft` pour ne créer que des brouillons au lieu d’envoyer.

### 2.2 Contacts : toutes les adresses, première en To et les autres en Cc

- **Règle** : toutes les adresses contact sont utilisées. **Première = To**, **suivantes = Cc** (brouillon J0 et toutes les relances).
- **Orchestrateur** : `_normalize_contacts()` ; `canal_application.contact_cible` (To) et `canal_application.contact_cc` (chaîne comma-separated). Enregistrement en base pour que followup_runner ait To + Cc.
- **Fichier URLs** : format `url	email1, email2` ou override `"email1, email2"` → To + Cc.
- **Drafting** : `create_draft(..., cc_emails=...)` et `send_email(..., cc_emails=...)`.
- **followup_runner** : lit `contact_cc` dans `result_json` et passe les Cc à chaque envoi.

### 2.3 CV et profil : A.P.S.I. 2015–2022 uniquement (plus 22 ans ni 2000–2022)

- **Source de vérité** : `resources/base_real.json` et `resources/cv_base_datas_pour_candidatures.json`.
- **A.P.S.I.** : période affichée **2015–2022** uniquement. Jamais « 22 ans », jamais « 2000–2022 » (CV rajeuni, psychologie candidature à partir de 2015).
- **Génération** : CvAtvGenerator, LmCoordinator, EmailEngine s’appuient sur la base ; `exposition_seniorite` par défaut = operationnelle ; `reference_canonique_periodes_roles` et personas (dont IT) avec `periode_apsi` = 2015–2022.
- **Anti-hallucination** : `exemples_interdits` et règles dans la base interdisent les formulations 22 ans / 2000–2022 pour l’APSI.

### 2.4 LLM et déploiement

- **LLM** : priorité **OpenAI (GPT)** si `OPENAI_API_KEY` ; sinon Groq. Fallback OpenAI sur 429.
- **Projet** : nom **« Environnement Python scalup et start up »** — `PROJECT.md`, `project_manifest.json`.

---

## 3. Où trouver le détail

| Thème | Fichiers |
|-------|----------|
| Workflow et règles globales | `AGENTS_ROADMAP.md` |
| Relances (commandes, cron) | `RELANCE_PROSPECTION.md` |
| Architecture des agents | `ARCHITECTURE_AGENTIQUE.md` |
| Dernières actions | `AGENTS_LOG.md` |
| Base de données profil (périodes, interdits) | `resources/base_real.json` (clés `regles_agent_orchestrateur`, `reference_canonique_periodes_roles`, `exposition_seniorite`) |

---

## 4. Mise à jour des directives

- Toute évolution de règle (relances, contacts, CV, LLM) doit être **consignée ici** et dans `AGENTS_LOG.md`.
- L’orchestrateur et le chef de projet s’assurent que le code et les autres docs (ROADMAP, RELANCE_PROSPECTION) restent alignés avec ce fichier.

---

*Dernière mise à jour : 2026-03-03. Entrée correspondante dans `AGENTS_LOG.md`.*
