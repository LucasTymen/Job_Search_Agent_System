"""
Cron dédié aux relances : J+2 (J2), J+4 (J1), J+7 (J1 bis), J+9 (J2 bis).
Par défaut : ENVOI automatique des relances (tu n'as rien à faire après J0).
Séquence : J0 → J2 → J1 → J1 → J2.
Usage : python -m scheduler.followup_runner [--dry-run] [--draft]
  --dry-run : simule sans envoyer
  --draft   : crée des brouillons au lieu d'envoyer (comportement ancien)
"""
import argparse
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STORAGE_DIR = PROJECT_ROOT / "storage"
LOGS_DIR = PROJECT_ROOT / "logs"

LOGS_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / "followup.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("followup_runner")


def _get_db_path() -> Path:
    return STORAGE_DIR / "applications.db"


def run_followups(db_path: Path | None = None, dry_run: bool = False, draft_only: bool = False) -> int:
    """
    Relances J0 → J2 → J1 → J1_bis → J2 à partir des candidatures en base.
    Par défaut : envoi réel des emails (plus besoin de s'en souvenir).
    - J+2 : status in ('J0','envoyee') et delta == 2 → envoi email_j2, status relance_j2
    - J+4 : status == 'relance_j2' et delta == 4 → envoi email_j1, status relance_j1
    - J+7 : status == 'relance_j1' et delta == 7 → envoi email_j1_bis, status relance_j1_bis
    - J+9 : status == 'relance_j1_bis' et delta >= 9 → envoi email_j2_bis, status relance_j2_bis
    draft_only=True : crée des brouillons au lieu d'envoyer.
    """
    db_file = db_path or _get_db_path()
    if not db_file.exists():
        log.warning("Base applications introuvable : %s", db_file)
        return 0

    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    today = datetime.now().date()
    sent = 0

    rows = conn.execute("""
        SELECT id, job_url, status, result_json, created_at
        FROM applications
        WHERE status IN ('J0', 'envoyee', 'relance_j2', 'relance_j1', 'relance_j1_bis')
        AND result_json IS NOT NULL
    """).fetchall()

    for row in rows:
        id_ = row["id"]
        job_url = row["job_url"]
        status = row["status"]
        result_json_str = row["result_json"]
        created_at_str = row["created_at"]

        try:
            s = (created_at_str or "")[:19].replace("Z", "+00:00")
            date_cand = datetime.fromisoformat(s).date()
        except (ValueError, TypeError):
            date_cand = datetime.fromisoformat((created_at_str or "")[:10]).date() if (created_at_str and len(created_at_str) >= 10) else None
        if not date_cand:
            continue

        try:
            data = json.loads(result_json_str)
        except (json.JSONDecodeError, TypeError):
            log.warning("JSON invalide id=%s", id_)
            continue

        offre = data.get("offre", {})
        canal = data.get("canal_application", {})
        emails = data.get("emails") or {}
        email_contact = canal.get("contact_cible") or data.get("email_trouve", {}).get("email_trouve") or ""
        cc_str = canal.get("contact_cc") or ""
        cc_list = [e.strip() for e in cc_str.split(",") if e.strip() and "@" in e] if cc_str else []
        if not email_contact or email_contact == "Inconnu":
            log.debug("Pas d'email pour id=%s %s", id_, offre.get("entreprise", "?"))
            continue

        entreprise = offre.get("entreprise", "?")
        titre = offre.get("titre", "?")
        mail_j2 = (emails.get("email_j2") or "").strip()
        mail_j1 = (emails.get("email_j1") or "").strip()
        mail_j1_bis = (emails.get("email_j1_bis") or "").strip()
        mail_j2_bis = (emails.get("email_j2_bis") or "").strip()
        sujet = (emails.get("sujet") or f"Relance candidature — {titre}").strip()

        delta = (today - date_cand).days

        if delta == 2 and status in ("J0", "envoyee") and mail_j2:
            log.info("Relance J+2 -> %s (%s)", entreprise, email_contact)
            if not dry_run:
                _do_followup(email_contact, sujet, mail_j2, "j2", draft_only=draft_only, cc_emails=cc_list)
                conn.execute("UPDATE applications SET status='relance_j2' WHERE id=?", (id_,))
                conn.commit()
                sent += 1

        elif delta == 4 and status == "relance_j2" and mail_j1:
            log.info("Relance J+4 (J1) -> %s (%s)", entreprise, email_contact)
            if not dry_run:
                _do_followup(email_contact, sujet, mail_j1, "j1", draft_only=draft_only, cc_emails=cc_list)
                conn.execute("UPDATE applications SET status='relance_j1' WHERE id=?", (id_,))
                conn.commit()
                sent += 1

        elif delta == 7 and status == "relance_j1" and mail_j1_bis:
            log.info("Relance J+7 (J1 bis) -> %s (%s)", entreprise, email_contact)
            if not dry_run:
                _do_followup(email_contact, sujet, mail_j1_bis, "j1_bis", draft_only=draft_only, cc_emails=cc_list)
                conn.execute("UPDATE applications SET status='relance_j1_bis' WHERE id=?", (id_,))
                conn.commit()
                sent += 1

        elif delta >= 9 and status == "relance_j1_bis" and mail_j2_bis:
            log.info("Relance J+9 (J2 bis) -> %s (%s)", entreprise, email_contact)
            if not dry_run:
                _do_followup(email_contact, sujet, mail_j2_bis, "j2_bis", draft_only=draft_only, cc_emails=cc_list)
                conn.execute("UPDATE applications SET status='relance_j2_bis' WHERE id=?", (id_,))
                conn.commit()
                sent += 1

    conn.close()
    log.info("Relances terminées — %d envoyées", sent)
    return sent


def _do_followup(to_email: str, subject: str, body: str, type_: str, draft_only: bool = False, cc_emails: list = None) -> None:
    """
    Envoie la relance (ou crée un brouillon si draft_only=True). To + Cc si plusieurs contacts.
    """
    from agents.drafting import GmailDraftingAgent

    agent = GmailDraftingAgent()
    prefix_map = {"j2": "J+2", "j1": "J+4 (J1)", "j1_bis": "J+7 (J1 bis)", "j2_bis": "J+9 (J2 bis)"}
    prefix = prefix_map.get(type_, type_)
    full_subject = f"Re: {subject}" if not subject.startswith("Re:") else subject
    cc_list = cc_emails or []

    if draft_only:
        agent.create_draft(to_email=to_email, subject=full_subject, body=body, attachment_paths=[], cc_emails=cc_list)
        log.info("Brouillon %s créé pour %s%s", prefix, to_email, " (+ Cc)" if cc_list else "")
    else:
        ok = agent.send_email(to_email=to_email, subject=full_subject, body=body, attachment_paths=[], cc_emails=cc_list)
        if ok:
            log.info("Relance %s envoyée à %s%s", prefix, to_email, " (+ Cc)" if cc_list else "")
        else:
            log.warning("Échec envoi %s pour %s", prefix, to_email)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Relances J+2, J+4, J+7, J+9 — envoi automatique (tu envoies J0, le reste part tout seul)."
    )
    parser.add_argument("--dry-run", action="store_true", help="Simule sans envoyer")
    parser.add_argument("--draft", action="store_true", help="Crée des brouillons au lieu d'envoyer")
    parser.add_argument("--db", help="Chemin vers applications.db")
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else None
    run_followups(db_path=db_path, dry_run=args.dry_run, draft_only=args.draft)


if __name__ == "__main__":
    main()
