#!/bin/bash
# A executer SUR le serveur Contabo (apres SSH).
# Non destructif : ne touche qu'a /opt/job_search_agent et aux containers job_agent*.
# Ne jamais arreter/modifier les containers SquidResearch.
# Backup automatique de storage/ avant deploy (conservation 5 derniers).

set -e
PROJECT_DIR="/opt/job_search_agent"
BACKUP_DIR="$PROJECT_DIR/backups"

log_ok()   { echo "[OK] $*"; }
log_warn() { echo "[WARN] $*"; }
log_err()  { echo "[ERR] $*"; }

check_squid_untouched() {
  docker ps -a --format "{{.Names}}" | grep -i squid || true
}

# Backup storage (applications.db, seen_jobs.db) — protecteur, jamais destructif
if [ -d "$PROJECT_DIR/storage" ]; then
  mkdir -p "$BACKUP_DIR"
  TS=$(date +%Y%m%d_%H%M%S)
  cp -a "$PROJECT_DIR/storage" "$BACKUP_DIR/storage_$TS" 2>/dev/null && log_ok "Backup storage -> $BACKUP_DIR/storage_$TS" || log_warn "Backup storage skipped"
  ls -dt "$BACKUP_DIR"/storage_* 2>/dev/null | tail -n +6 | xargs -r rm -rf 2>/dev/null || true
fi

if [ ! -f "$PROJECT_DIR/docker-compose.yml" ]; then
  log_err "Absent: $PROJECT_DIR/docker-compose.yml"
  exit 1
fi

cd "$PROJECT_DIR"
log_ok "Repertoire: $PROJECT_DIR"
echo "--- Avant ---"
check_squid_untouched

log_ok "docker compose up -d --build"
docker compose up -d --build

echo "--- Containers job_agent ---"
docker ps --filter "name=job_agent" --format "table {{.Names}}\t{{.Status}}"
echo "--- Apres (SquidResearch inchange) ---"
check_squid_untouched

if docker ps --format "{{.Names}}" | grep -q job_agent_cron; then
  log_ok "Dry-run cron..."
  docker exec job_agent_cron python -m scheduler.cron_runner --sources wttj,francetravail --dry-run --max 2 || true
  log_ok "Dry-run followup..."
  docker exec job_agent_cron python -m scheduler.followup_runner --dry-run || true
fi
log_ok "Fin deploiement securise."
