# Déploiement production — Procédure sécurisée

> **Principe : protecteur, jamais destructif. Aucune perte de données.**

---

## Résumé des risques et protections

| Élément | Risque | Protection |
|---------|--------|------------|
| `applications.db` | Perte des candidatures | Tar exclut `*.db` — jamais écrasé. Backup avant déploiement. |
| `seen_jobs.db` | Perte de la déduplication | Idem. Backup avant déploiement. |
| `.env` | Clés exposées | Tar exclut `.env` — jamais transféré. |
| SquidResearch | Containers modifiés | Script ne touche qu'à `job_agent*`. |
| Logs | Perte d'historique | Tar exclut `*.log`. Backup optionnel. |

**Pas de migrations destructives :** schémas SQLite avec `CREATE TABLE IF NOT EXISTS` uniquement.

---

## Étape 1 — Backup sur le serveur (OBLIGATOIRE)

```bash
ssh root@173.249.4.106

# Créer un backup daté (ne supprime rien)
cd /opt/job_search_agent
BACKUP_DIR="/opt/job_search_agent/backups"
mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
cp -a storage "$BACKUP_DIR/storage_$TIMESTAMP" 2>/dev/null || true
# Conserver les 5 derniers backups
ls -dt $BACKUP_DIR/storage_* 2>/dev/null | tail -n +6 | xargs -r rm -rf
```

---

## Étape 2 — Transfert (depuis ta machine)

Le `tar` exclut `.env`, `venv`, `*.db`, `*.log` : **les données sur le serveur ne sont pas écrasées.**

```powershell
cd C:\Users\Lucas\.gemini\antigravity\brain\c718aa18-28de-4cd5-9403-f4be6c1ae8db\Job_Search_Agent_System

.\scripts\contabo_ssh_chain.ps1
```

Ou manuellement :

```powershell
tar --exclude=.env --exclude=venv --exclude=.git --exclude=__pycache__ --exclude=.pytest_cache --exclude=htmlcov --exclude="*.db" --exclude="*.log" -cvf - . | ssh root@173.249.4.106 "mkdir -p /opt/job_search_agent && cd /opt/job_search_agent && tar -xvf -"
```

---

## Étape 3 — Déploiement sur le serveur (après transfert)

```bash
ssh root@173.249.4.106
cd /opt/job_search_agent

# Vérifier que SquidResearch n'est pas touché
docker ps -a | grep squid

# Lancer le script safe (build + up, sans toucher à SquidResearch)
bash scripts/contabo_safe_deploy.sh
```

Le script :
- Ne modifie que les containers `job_agent*`
- Ne touche pas à SquidResearch
- Lance un dry-run après le build pour vérifier

---

## Étape 4 — Vérifications post-déploiement

```bash
# Containers job_agent actifs
docker ps --filter name=job_agent

# Test cron (dry-run)
docker exec job_agent_cron python -m scheduler.cron_runner --sources wttj --dry-run --max 2

# Logs
docker logs --tail 30 job_telegram_bot
docker exec job_agent_cron tail -20 /app/logs/cron.log

# Vérifier que applications.db est toujours là
docker exec job_agent_cron ls -la /app/storage/
```

---

## Rollback (en cas de problème)

```bash
# Restaurer le backup storage si nécessaire
cp -a /opt/job_search_agent/backups/storage_YYYYMMDD_HHMMSS/* /opt/job_search_agent/storage/

# Redémarrer les containers
cd /opt/job_search_agent
docker compose restart
```

---

## Déploiement automatique (GitHub Actions)

Un push sur `main` déclenche le workflow `.github/workflows/deploy.yml` : transfert tar + `contabo_safe_deploy.sh`.

**Configuration (une seule fois) :**

1. GitHub → Repo → **Settings** → **Secrets and variables** → **Actions**
2. Ajouter les secrets :
   | Secret | Valeur | Exemple |
   |--------|--------|---------|
   | `SSH_HOST` | IP du serveur | `173.249.4.106` |
   | `SSH_USER` | Utilisateur SSH | `root` |
   | `SSH_PRIVATE_KEY` | Contenu de la clé privée | Copier tout le fichier `id_ed25519_contabo` ou `id_rsa_contabo` |

3. S’assurer que la clé publique est autorisée sur le serveur : `~/.ssh/authorized_keys`

**Déclenchement manuel :** Actions → Deploy to Contabo → Run workflow

---

## Checklist avant push prod

- [ ] Backup storage fait sur le serveur (automatique dans `contabo_safe_deploy.sh`)
- [ ] .env présent sur le serveur (vérifier : `ssh ... "test -f /opt/job_search_agent/.env && echo OK"`)
- [ ] SquidResearch non ciblé
