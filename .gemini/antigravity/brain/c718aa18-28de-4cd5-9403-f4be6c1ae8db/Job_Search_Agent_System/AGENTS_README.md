# Coordination entre agents IA

> Point d'entrée pour tout agent IA travaillant sur ce projet.

## Orchestrateur et chef de projet

**L'orchestrateur** (`core/orchestrator.py`) et **le chef de projet** (coordination sprints, RACI) doivent **prendre connaissance de [AGENTS_DIRECTIVES.md](AGENTS_DIRECTIVES.md) en priorité**, appliquer les directives qui s'imposent selon les cas, et **informer les autres agents** (génération, matching, drafting, followup, Telegram) pour que les règles soient respectées partout.

## Fichiers à consulter

| Fichier | Usage |
|---------|-------|
| **[AGENTS_DIRECTIVES.md](AGENTS_DIRECTIVES.md)** | **Directives en vigueur** — relances auto, To/Cc, CV 2015–2022. À lire en priorité par orchestrateur et chef de projet. |
| **[AGENTS_ROADMAP.md](AGENTS_ROADMAP.md)** | Architecture, règles, workflow |
| **[AGENTS_LOG.md](AGENTS_LOG.md)** | Journal des actions réalisées — historique et handoff |
| **[AGENTS_TODO.md](AGENTS_TODO.md)** | Tâches en attente — phases 2, 3, 4 et backlog |

## Workflow rapide

1. **Orchestrateur / chef de projet :** lire `AGENTS_DIRECTIVES.md`, puis propager les consignes aux autres selon le périmètre.
2. Lire `AGENTS_ROADMAP.md`
3. Consulter `AGENTS_LOG.md` (dernières actions)
4. Choisir une tâche dans `AGENTS_TODO.md`
5. Après action : mettre à jour `AGENTS_LOG.md` + `AGENTS_TODO.md`
