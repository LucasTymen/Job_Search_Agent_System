"""
Script batch : candidater sur une liste d'URLs, créer les brouillons Gmail (J0)
et enregistrer en base pour déclencher la séquence de relances (J+2, J+4, J+7, J+9).

Usage:
  python scripts/batch_apply_urls.py --file urls.txt [--no-draft] [--dry-run]
  python scripts/batch_apply_urls.py --url "https://..." --url "https://..." ...
  python scripts/batch_apply_urls.py   # lit urls_batch.txt par défaut si présent

Chaque URL subit : extraction → matching → génération CV/LM/emails → (optionnel) brouillon → save_application.
Les relances sont gérées par : python -m scheduler.followup_runner [--dry-run]
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

STORAGE_DIR = PROJECT_ROOT / "storage"
RESOURCES_DIR = PROJECT_ROOT / "resources"
REPORTS_DIR = PROJECT_ROOT / "reports"
DEFAULT_URLS_FILE = PROJECT_ROOT / "urls_batch.txt"


def load_base_json():
    for name in ("base_real.json", "cv_base_datas_pour_candidatures.json", "base.json"):
        path = RESOURCES_DIR / name
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError("Aucun profil dans resources/ (base_real.json, base.json)")


def load_urls_from_file(path: Path) -> list[str]:
    urls = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and (line.startswith("http://") or line.startswith("https://")):
                urls.append(line)
    return urls


def load_urls_contacts_from_file(path: Path) -> list[tuple[str, str | None]]:
    """
    Charge des lignes URL [tab|virgule] email.
    Retourne une liste de (url, email ou None).
    """
    out = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            email = None
            if "\t" in line:
                parts = line.split("\t", 1)
                url_part, email_part = parts[0].strip(), (parts[1].strip() if len(parts) > 1 else "")
                if url_part.startswith(("http://", "https://")):
                    if email_part and "@" in email_part:
                        email = email_part
                    out.append((url_part, email))
            elif "," in line:
                parts = line.split(",", 1)
                url_part, email_part = parts[0].strip(), (parts[1].strip() if len(parts) > 1 else "")
                if url_part.startswith(("http://", "https://")):
                    if email_part and "@" in email_part:
                        email = email_part
                    out.append((url_part, email))
            elif line.startswith(("http://", "https://")):
                out.append((line, None))
    return out


def run_one(url: str, create_draft: bool, base_json: dict, email_override: str | None = None) -> dict:
    """
    Lance pipeline + save_application pour une URL.
    Retourne dict avec ok, entreprise, titre, action, draft_created, error, elapsed_sec.
    """
    from core.orchestrator import Orchestrator
    from storage.db import save_application

    out = {"url": url, "ok": False, "entreprise": "?", "titre": "?", "action": "?", "draft_created": False, "error": None, "elapsed_sec": None}
    start = time.perf_counter()
    try:
        orchestrator = Orchestrator(base_json=base_json)
        result = orchestrator.run_pipeline(url, create_draft=create_draft, email_override=email_override)
        save_application(result, url, db_path=str(STORAGE_DIR))
        out["ok"] = True
        out["entreprise"] = (result.offre or {}).get("entreprise", "?")
        out["titre"] = (result.offre or {}).get("titre", "?")
        out["action"] = result.next_action or "?"
        email_dest = (result.email_trouve or {}).get("email_trouve") if isinstance(result.email_trouve, dict) else None
        if isinstance(email_dest, str):
            email_dest = email_dest.strip() or None
        if email_dest and email_dest.lower() in ("none", "inconnu", "n/a"):
            email_dest = None
        out["draft_created"] = bool(create_draft and result.next_action == "POSTULER" and email_dest)
        return out
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)}"
        return out
    finally:
        out["elapsed_sec"] = round(time.perf_counter() - start, 1)


def main():
    parser = argparse.ArgumentParser(description="Batch candidatures + brouillons + enregistrement pour relances")
    parser.add_argument("--file", "-f", type=Path, help="Fichier contenant une URL par ligne, ou URL[tab|virgule]email")
    parser.add_argument("--url", "-u", action="append", dest="urls", help="URL(s) à traiter (répétable)")
    parser.add_argument("--no-draft", action="store_true", help="Ne pas créer les brouillons Gmail")
    parser.add_argument("--dry-run", action="store_true", help="Affiche les URLs sans lancer le pipeline")
    parser.add_argument("--max", type=int, default=0, help="Limiter à N URLs (0 = toutes)")
    args = parser.parse_args()

    url_tuples: list[tuple[str, str | None]] = []
    if args.urls:
        url_tuples = [(u.strip(), None) for u in args.urls if u and u.strip().startswith(("http://", "https://"))]
    if not url_tuples and args.file and args.file.exists():
        url_tuples = load_urls_contacts_from_file(args.file)
        if not url_tuples:
            url_tuples = [(u, None) for u in load_urls_from_file(args.file)]
    if not url_tuples and DEFAULT_URLS_FILE.exists():
        url_tuples = load_urls_contacts_from_file(DEFAULT_URLS_FILE)
        if not url_tuples:
            url_tuples = [(u, None) for u in load_urls_from_file(DEFAULT_URLS_FILE)]
    if not url_tuples:
        print("Aucune URL fournie. Utilisez --file urls.txt ou --url 'https://...' [--url '...']")
        print("Fichier optionnel : url\temail ou url,email par ligne pour forcer le contact.")
        sys.exit(1)

    if args.max and args.max > 0:
        url_tuples = url_tuples[: args.max]

    print(f"--- Batch : {len(url_tuples)} URL(s) | create_draft={not args.no_draft} ---")
    if args.dry_run:
        for i, (u, em) in enumerate(url_tuples, 1):
            print(f"  {i}. {u[:70]}..." + (f" -> {em}" if em else ""))
        print("Dry-run : aucun pipeline exécuté.")
        return

    try:
        base_json = load_base_json()
    except FileNotFoundError as e:
        print(f"Erreur : {e}")
        sys.exit(1)

    results = []
    total_start = time.perf_counter()
    for i, (url, email_override) in enumerate(url_tuples, 1):
        print(f"[{i}/{len(url_tuples)}] {url[:70]}..." + (f" -> {email_override}" if email_override else ""))
        r = run_one(url, create_draft=not args.no_draft, base_json=base_json, email_override=email_override)
        results.append(r)
        elapsed = r.get("elapsed_sec")
        if r["ok"]:
            print(f"  OK — {r['entreprise']} | {r['titre']} | {r['action']}" + (" | Brouillon créé" if r["draft_created"] else "") + (f" ({elapsed}s)" if elapsed is not None else ""))
        else:
            print(f"  ÉCHEC — {r['error']}" + (f" ({elapsed}s)" if elapsed is not None else ""))
    total_elapsed = round(time.perf_counter() - total_start, 1)

    # Rapport
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"batch_report_{ts}.json"
    report_md_path = REPORTS_DIR / f"batch_report_{ts}.md"

    summary = {
        "date": datetime.now().isoformat(),
        "total": len(url_tuples),
        "ok": sum(1 for r in results if r["ok"]),
        "failed": sum(1 for r in results if not r["ok"]),
        "drafts_created": sum(1 for r in results if r.get("draft_created")),
        "total_elapsed_sec": total_elapsed,
        "results": results,
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # Rapport Markdown lisible
    md_lines = [
        "# Rapport batch candidatures",
        f"**Date** : {summary['date']}",
        f"**Total** : {summary['total']} | **OK** : {summary['ok']} | **Échecs** : {summary['failed']} | **Brouillons** : {summary['drafts_created']} | **Durée totale** : {summary.get('total_elapsed_sec', '—')} s",
        "",
        "## Détail par URL",
        "",
    ]
    for r in results:
        status = "OK" if r["ok"] else "ÉCHEC"
        draft = " | Brouillon créé" if r.get("draft_created") else ""
        err = f" | `{r['error']}`" if r.get("error") else ""
        sec = f" ({r.get('elapsed_sec')} s)" if r.get("elapsed_sec") is not None else ""
        md_lines.append(f"- **{status}** — {r['entreprise']} — {r['titre']} | {r['action']}{draft}{err}{sec}")
        md_lines.append(f"  - `{r['url'][:90]}...`")
    md_lines.extend([
        "",
        "## Relances",
        "Les candidatures enregistrées seront reprises par la séquence de relances. Lancer :",
        "```",
        "python -m scheduler.followup_runner   # ou --dry-run pour simuler",
        "```",
    ])
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"\n--- Terminé : {summary['ok']} OK, {summary['failed']} échec(s), {summary['drafts_created']} brouillon(s) — durée {total_elapsed} s ---")
    print(f"Rapport : {report_path}")
    print(f"Rapport MD : {report_md_path}")
    print("Relances : python -m scheduler.followup_runner")


if __name__ == "__main__":
    main()
