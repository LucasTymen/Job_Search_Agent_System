"""
Découverte des offres par source — WTTJ (Playwright SPA), France Travail (requests).
URLs configurables — pas d'URL unique hardcodée.
"""
import random
import time
from typing import Any

import requests
from bs4 import BeautifulSoup

SOURCES: dict[str, dict[str, Any]] = {
    "wttj": {
        "queries": ["growth engineer", "developpeur python", "automatisation"],
        "base": "https://www.welcometothejungle.com",
    },
    "francetravail": {
        "urls": [
            "https://candidat.francetravail.fr/offres/recherche?motsCles=growth+engineer",
            "https://candidat.francetravail.fr/offres/recherche?motsCles=developpeur+python",
        ],
        "base": "https://candidat.francetravail.fr",
    },
    "indeed": {
        "base": "https://fr.indeed.com",
        "url_tpl": "https://fr.indeed.com/jobs?q={query}&l=France",
    },
    "hellowork": {
        "base": "https://www.hellowork.com",
        "urls": [
            "https://www.hellowork.com/fr-fr/emploi/metier_developpeur-informatique.html",
            "https://www.hellowork.com/fr-fr/emploi/metier_ingenieur.html",
            "https://www.hellowork.com/fr-fr/emploi/mot-cle_cdi.html",
        ],
    },
    "dogfinance": {
        "base": "https://dogfinance.com",
        "url_tpl": "https://dogfinance.com/en/offres?page={page}",
    },
    "meteojob": {
        "base": "https://www.meteojob.com",
        "urls": [
            "https://www.meteojob.com/jobs",
            "https://www.meteojob.com/Emploi-developpeur",
        ],
    },
    "glassdoor": {
        "base": "https://www.glassdoor.com",
        "url_tpl": "https://www.glassdoor.com/Job/france-{query}-jobs-SRCH_IL.0,6_IN86.htm",
    },
    "linkedin": {
        "base": "https://www.linkedin.com",
        "url_tpl": "https://www.linkedin.com/jobs/search/?keywords={query}&location=France",
    },
    "chooseyourboss": {
        "base": "https://www.chooseyourboss.com",
        "urls": [
            "https://www.chooseyourboss.com/offres/emploi-it",
        ],
    },
    "apec": {
        "base": "https://www.apec.fr",
        "urls": [
            "https://www.apec.fr/parcourir-les-emplois.html",
            "https://www.apec.fr/candidat/recherche-emploi.html/emploi?motsCles=developpeur+python",
            "https://www.apec.fr/candidat/recherche-emploi.html/emploi?motsCles=ingenieur",
        ],
    },
    "manpower": {
        "base": "https://www.manpower.fr",
        "urls": [
            "https://www.manpower.fr/offre-emploi/",
            "https://www.manpower.fr/offre-emploi/?keywords=developpeur",
            "https://www.manpower.fr/offre-emploi/?keywords=ingenieur",
        ],
    },
    "adecco": {
        "base": "https://www.adecco.fr",
        "urls": [
            "https://www.adecco.fr/fr-fr/emploi/",
            "https://www.adecco.fr/fr-fr/emploi/recherche?keywords=developpeur",
            "https://www.adecco.fr/fr-fr/emploi/recherche?keywords=technicien",
        ],
    },
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}


def _discover_jobs_wttj_playwright(query: str, max_jobs: int) -> list[str]:
    """WTTJ SPA React — Playwright pour rendu JS."""
    from playwright.sync_api import sync_playwright

    url = f"https://www.welcometothejungle.com/fr/jobs?query={query.replace(' ', '+')}&page=1"
    urls: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        # load au lieu de networkidle : évite blocage sur SPA avec polling infini
        page.goto(url, wait_until="load", timeout=25000)
        time.sleep(2)  # lazy load minimal

        links = page.query_selector_all("a[href*='/fr/companies/'][href*='/jobs/']")
        for link in links:
            href = link.get_attribute("href")
            if not href:
                continue
            path = href.split("?")[0].rstrip("/")
            if path.endswith("/jobs"):
                continue
            if "/fr/pages/" in href:
                continue
            if "/jobs/" not in path:
                continue
            job_slug = path.split("/jobs/", 1)[1].split("/")[0]
            if not job_slug:
                continue
            full = "https://www.welcometothejungle.com" + href if href.startswith("/") else href
            if full not in urls:
                urls.append(full)
            if len(urls) >= max_jobs:
                break

        browser.close()
    return urls


def _build_francetravail_urls(queries: list[str]) -> list[str]:
    """Construit les URLs France Travail depuis les requêtes."""
    base = SOURCES["francetravail"]["base"]
    return [f"{base}/offres/recherche?motsCles={q.replace(' ', '+')}" for q in queries]


def _discover_jobs_francetravail(max_jobs: int, base_json: dict | None = None) -> list[str]:
    """France Travail — requests + BeautifulSoup."""
    from scheduler.persona_queries import get_persona_queries

    urls: list[str] = []
    seen: set[str] = set()

    listing_urls = (
        _build_francetravail_urls(get_persona_queries(base_json, 2))
        if base_json
        else SOURCES["francetravail"]["urls"]
    )

    for listing_url in listing_urls:
        if len(urls) >= max_jobs:
            break
        try:
            time.sleep(random.uniform(2, 5))
            r = requests.get(listing_url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            links = soup.select("a[href*='/offres/recherche/detail/']")

            for a in links:
                href = a.get("href", "")
                if not href or href in seen:
                    continue
                base = SOURCES["francetravail"]["base"]
                full = base + href if href.startswith("/") else href
                seen.add(href)
                urls.append(full)
                if len(urls) >= max_jobs:
                    return urls
        except Exception as e:
            print(f"[discoverer] Erreur France Travail {listing_url} : {e}")

    return urls


def _discover_jobs_indeed(max_jobs: int, base_json: dict | None = None) -> list[str]:
    """Indeed France — requests + BeautifulSoup (peut 403 selon anti-bot)."""
    from scheduler.persona_queries import get_persona_queries

    queries = (
        get_persona_queries(base_json, max_per_persona=2)
        if base_json
        else ["developpeur python", "growth", "technicien support"]
    )
    urls: list[str] = []
    seen: set[str] = set()
    base = SOURCES["indeed"]["base"]
    tpl = SOURCES["indeed"]["url_tpl"]

    for q in queries[:4]:
        if len(urls) >= max_jobs:
            break
        url = tpl.format(query=q.replace(" ", "+"))
        try:
            time.sleep(random.uniform(2, 5))
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select("a[href*='/rc/clk'], a[href*='/viewjob'], a[href*='/pagead/clk']"):
                href = a.get("href", "")
                if not href or "indeed.com" not in href:
                    continue
                full = base + href if href.startswith("/") else href
                if full not in seen:
                    seen.add(full)
                    urls.append(full)
                if len(urls) >= max_jobs:
                    return urls
        except Exception as e:
            print(f"[discoverer] Erreur Indeed {url[:60]} : {e}")

    return urls


def _discover_jobs_chooseyourboss(max_jobs: int, base_json: dict | None = None) -> list[str]:
    """ChooseYourBoss — requests + BeautifulSoup."""
    urls: list[str] = []
    seen: set[str] = set()
    base_site = SOURCES["chooseyourboss"]["base"]
    listing_urls = SOURCES["chooseyourboss"].get("urls", [f"{base_site}/offres/emploi-it"])

    for url in listing_urls:
        if len(urls) >= max_jobs:
            break
        try:
            time.sleep(random.uniform(2, 5))
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select("a[href*='/candidates/offers/']"):
                href = a.get("href", "")
                if not href or href in seen:
                    continue
                if not href.startswith("http"):
                    full = base_site + href if href.startswith("/") else href
                else:
                    full = href
                seen.add(href)
                urls.append(full)
                if len(urls) >= max_jobs:
                    return urls
        except Exception as e:
            print(f"[discoverer] Erreur ChooseYourBoss : {e}")

    return urls


def _discover_jobs_hellowork(max_jobs: int, base_json: dict | None = None) -> list[str]:
    """HelloWork — requests + BeautifulSoup. Collecte uniquement /emplois/[id].html (offres individuelles)."""
    urls: list[str] = []
    seen: set[str] = set()
    base_site = SOURCES["hellowork"]["base"]
    listing_urls = SOURCES["hellowork"].get("urls", [])

    for url in listing_urls:
        if len(urls) >= max_jobs:
            break
        try:
            time.sleep(random.uniform(2, 5))
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select("a[href*='/emplois/']"):
                href = a.get("href", "")
                if not href or href in seen:
                    continue
                full = base_site + href if href.startswith("/") else href
                if "/emplois/" in full and ".html" in full and full not in seen:
                    seen.add(href)
                    urls.append(full)
                if len(urls) >= max_jobs:
                    return urls
        except Exception as e:
            print(f"[discoverer] Erreur HelloWork : {e}")

    return urls[:max_jobs]


def _discover_jobs_dogfinance(max_jobs: int, base_json: dict | None = None) -> list[str]:
    """Dogfinance / emploi.agefi.fr — requests + BeautifulSoup."""
    urls: list[str] = []
    seen: set[str] = set()

    for page in range(1, 4):
        if len(urls) >= max_jobs:
            break
        try:
            time.sleep(random.uniform(2, 5))
            url = f"https://dogfinance.com/en/offres?page={page}"
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select("a[href*='/offres/'], a[href*='emploi.agefi.fr'], a[href*='/offre/']"):
                href = a.get("href", "")
                if not href or href in seen:
                    continue
                if "offres?" in href or "page=" in href:
                    continue
                full = href if href.startswith("http") else f"https://emploi.agefi.fr{href}" if "agefi" in href else f"https://dogfinance.com{href}"
                seen.add(href)
                urls.append(full)
                if len(urls) >= max_jobs:
                    return urls
        except Exception as e:
            print(f"[discoverer] Erreur Dogfinance : {e}")

    return urls


def _discover_jobs_meteojob(max_jobs: int, base_json: dict | None = None) -> list[str]:
    """Meteojob — requests + BeautifulSoup."""
    urls: list[str] = []
    seen: set[str] = set()
    base_site = SOURCES["meteojob"]["base"]
    listing_urls = SOURCES["meteojob"].get("urls", ["https://www.meteojob.com/jobs"])

    for url in listing_urls:
        if len(urls) >= max_jobs:
            break
        try:
            time.sleep(random.uniform(2, 5))
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select("a[href*='/emploi/'], a[href*='/Emploi/'], a[href*='/job/']"):
                href = a.get("href", "")
                if not href or href in seen:
                    continue
                full = base_site + href if href.startswith("/") else href
                if "meteojob.com" not in full:
                    continue
                seen.add(href)
                urls.append(full)
                if len(urls) >= max_jobs:
                    return urls
        except Exception as e:
            print(f"[discoverer] Erreur Meteojob : {e}")

    return urls


def _discover_jobs_glassdoor(max_jobs: int, base_json: dict | None = None) -> list[str]:
    """Glassdoor — requests + BeautifulSoup (peut bloquer)."""
    from scheduler.persona_queries import get_persona_queries

    queries = get_persona_queries(base_json, max_per_persona=2) if base_json else ["python", "developer", "data"]
    urls: list[str] = []
    seen: set[str] = set()
    tpl = SOURCES["glassdoor"]["url_tpl"]

    for q in queries[:3]:
        if len(urls) >= max_jobs:
            break
        try:
            time.sleep(random.uniform(3, 6))
            url = tpl.format(query=q.replace(" ", "-"))
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select("a[href*='/Job/'], a[href*='job-listing']"):
                href = a.get("href", "")
                if not href or "glassdoor.com" not in href or href in seen:
                    continue
                if "jobs-SRCH" in href:
                    continue
                full = href if href.startswith("http") else "https://www.glassdoor.com" + href
                seen.add(href)
                urls.append(full)
                if len(urls) >= max_jobs:
                    return urls
        except Exception as e:
            print(f"[discoverer] Erreur Glassdoor : {e}")

    return urls


def _discover_jobs_linkedin(max_jobs: int, base_json: dict | None = None) -> list[str]:
    """LinkedIn Jobs — requests (très restrictif, peut 403). Playwright recommandé."""
    from scheduler.persona_queries import get_persona_queries

    queries = get_persona_queries(base_json, max_per_persona=2) if base_json else ["python", "developer"]
    urls: list[str] = []
    seen: set[str] = set()
    tpl = SOURCES["linkedin"]["url_tpl"]

    for q in queries[:3]:
        if len(urls) >= max_jobs:
            break
        try:
            time.sleep(random.uniform(3, 6))
            url = tpl.format(query=q.replace(" ", "+"))
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select("a[href*='/jobs/view/'], a[href*='/job/']"):
                href = a.get("href", "")
                if not href or "linkedin.com" not in href or href in seen:
                    continue
                full = href.split("?")[0] if "?" in href else href
                if full not in seen:
                    seen.add(href)
                    urls.append(full)
                if len(urls) >= max_jobs:
                    return urls
        except Exception as e:
            print(f"[discoverer] Erreur LinkedIn : {e}")

    return urls


def _discover_jobs_apec(max_jobs: int, base_json: dict | None = None) -> list[str]:
    """APEC — offres emploi cadres. URLs /emploi/detail-offre/[id]."""
    from scheduler.persona_queries import get_persona_queries

    urls: list[str] = []
    seen: set[str] = set()
    base_site = SOURCES["apec"]["base"]
    listing_urls = SOURCES["apec"].get("urls", [])

    if base_json:
        queries = get_persona_queries(base_json, max_per_persona=2)
        listing_urls = [
            f"{base_site}/candidat/recherche-emploi.html/emploi?motsCles={q.replace(' ', '+')}"
            for q in queries[:3]
        ]

    for url in listing_urls:
        if len(urls) >= max_jobs:
            break
        try:
            time.sleep(random.uniform(2, 5))
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select("a[href*='/detail-offre/']"):
                href = a.get("href", "")
                if not href or href in seen:
                    continue
                full = base_site + href if href.startswith("/") else href
                if full not in seen:
                    seen.add(href)
                    urls.append(full)
                if len(urls) >= max_jobs:
                    return urls
        except Exception as e:
            print(f"[discoverer] Erreur APEC : {e}")

    return urls


def _discover_jobs_manpower(max_jobs: int, base_json: dict | None = None) -> list[str]:
    """Manpower France — offres intérim, CDI, CDD. requests + BeautifulSoup."""
    urls: list[str] = []
    seen: set[str] = set()
    base_site = SOURCES["manpower"]["base"]
    listing_urls = SOURCES["manpower"].get("urls", [f"{base_site}/offre-emploi/"])

    for url in listing_urls:
        if len(urls) >= max_jobs:
            break
        try:
            time.sleep(random.uniform(2, 5))
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select("a[href*='/offre-emploi/'], a[href*='/offre/'], a[href*='/job/']"):
                href = a.get("href", "")
                if not href:
                    continue
                full = href if href.startswith("http") else base_site + href
                if "manpower.fr" not in full or full in seen:
                    continue
                if full == url or "offre-emploi?" in full or "keywords=" in full:
                    continue
                seen.add(full)
                urls.append(full)
                if len(urls) >= max_jobs:
                    return urls
        except Exception as e:
            print(f"[discoverer] Erreur Manpower : {e}")

    return urls


def _discover_jobs_adecco(max_jobs: int, base_json: dict | None = None) -> list[str]:
    """Adecco France — offres intérim, CDI, CDD. requests + BeautifulSoup."""
    urls: list[str] = []
    seen: set[str] = set()
    base_site = SOURCES["adecco"]["base"]
    listing_urls = SOURCES["adecco"].get("urls", [f"{base_site}/fr-fr/emploi/"])

    for url in listing_urls:
        if len(urls) >= max_jobs:
            break
        try:
            time.sleep(random.uniform(2, 5))
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select("a[href*='/offre/'], a[href*='/emploi/'], a[href*='/job/'], a[href*='adecco.fr/fr-fr']"):
                href = a.get("href", "")
                if not href:
                    continue
                full = href if href.startswith("http") else base_site + href
                if "adecco.fr" not in full or full in seen:
                    continue
                if full == url or "recherche" in full or "keywords=" in full:
                    continue
                if "/offre/" in full or "/emploi/" in full:
                    seen.add(full)
                    urls.append(full)
                if len(urls) >= max_jobs:
                    return urls
        except Exception as e:
            print(f"[discoverer] Erreur Adecco : {e}")

    return urls


# ---------------------------------------------------------------------------
# Extraction depuis une URL de page de recherche (user-pasted)
# ---------------------------------------------------------------------------

def is_search_page(url: str) -> bool:
    """
    Détecte si l'URL pointe vers une page de recherche/listing (et non une fiche d'offre).
    """
    u = url.lower()
    # Glassdoor (com + fr) : SRCH_IL, emplois-SRCH = page de recherche
    if "glassdoor" in u and ("srch_il" in u or "emplois-srch" in u):
        return True
    # Indeed : /jobs? = page de résultats
    if "indeed" in u and "/jobs?" in u:
        return True
    # France Travail : /offres/recherche? (pas /detail/)
    if "francetravail" in u and "/offres/recherche" in u and "/detail/" not in u:
        return True
    # WTTJ : /jobs? ou /fr/jobs? = listing
    if "welcometothejungle" in u and "/jobs" in u and "query=" in u:
        return True
    # HelloWork : /emploi/metier_ ou /emploi/mot-cle_ = listing
    if "hellowork" in u and ("/emploi/metier_" in u or "/emploi/mot-cle_" in u):
        return True
    # Meteojob : /jobs ou /emploi- sans id
    if "meteojob" in u and ("/jobs" in u or "/emploi-" in u):
        return True
    # ChooseYourBoss : /offres/emploi
    if "chooseyourboss" in u and "/offres/" in u and "/candidates/offers/" not in u:
        return True
    # APEC : parcourir, recherche-emploi
    if "apec" in u and ("parcourir" in u or "recherche-emploi" in u):
        return True
    # Manpower : /offre-emploi/ ou /offre-emploi? = listing
    if "manpower" in u and "/offre-emploi" in u:
        return True
    # Adecco : /emploi/ ou /emploi/recherche = listing
    if "adecco" in u and "/emploi" in u and "/offre/" not in u:
        return True
    # Dogfinance : /en/offres? = listing
    if "dogfinance" in u and "/offres" in u and "?page=" in u:
        return True
    # LinkedIn Jobs search
    if "linkedin" in u and "/jobs/search" in u:
        return True
    return False


def _extract_from_page_glassdoor(url: str, max_jobs: int) -> list[str]:
    """Extrait les URLs d'annonces depuis une page de recherche Glassdoor."""
    urls: list[str] = []
    seen: set[str] = set()
    try:
        time.sleep(random.uniform(2, 4))
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select("a[href*='/Job/'], a[href*='job-listing'], a[href*='voir-emploi']"):
            href = a.get("href", "")
            if not href or href in seen:
                continue
            if "jobs-SRCH" in href or "emplois-SRCH" in href:
                continue
            if "glassdoor" not in href.lower():
                base = "https://www.glassdoor.fr" if "glassdoor.fr" in url.lower() else "https://www.glassdoor.com"
                full = base + href if href.startswith("/") else href
            else:
                full = href if href.startswith("http") else "https://www.glassdoor.com" + href
            if full not in seen:
                seen.add(href)
                urls.append(full)
            if len(urls) >= max_jobs:
                return urls
    except Exception as e:
        print(f"[search_extract] Glassdoor {url[:60]} : {e}")
    return urls


def _extract_from_page_indeed(url: str, max_jobs: int) -> list[str]:
    """Extrait les URLs d'annonces depuis une page de recherche Indeed."""
    urls: list[str] = []
    seen: set[str] = set()
    base = "https://fr.indeed.com"
    try:
        time.sleep(random.uniform(2, 4))
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select("a[href*='/rc/clk'], a[href*='/viewjob'], a[href*='/pagead/clk']"):
            href = a.get("href", "")
            if not href or "indeed.com" not in href:
                continue
            full = base + href if href.startswith("/") else href
            if full not in seen:
                seen.add(full)
                urls.append(full)
            if len(urls) >= max_jobs:
                return urls
    except Exception as e:
        print(f"[search_extract] Indeed {url[:60]} : {e}")
    return urls


def _extract_from_page_francetravail(url: str, max_jobs: int) -> list[str]:
    """Extrait les URLs d'annonces depuis une page de recherche France Travail."""
    urls: list[str] = []
    seen: set[str] = set()
    base = SOURCES["francetravail"]["base"]
    try:
        time.sleep(random.uniform(2, 4))
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select("a[href*='/offres/recherche/detail/']"):
            href = a.get("href", "")
            if not href or href in seen:
                continue
            full = base + href if href.startswith("/") else href
            seen.add(href)
            urls.append(full)
            if len(urls) >= max_jobs:
                return urls
    except Exception as e:
        print(f"[search_extract] France Travail {url[:60]} : {e}")
    return urls


def _extract_from_page_wttj(url: str, max_jobs: int) -> list[str]:
    """WTTJ SPA — Playwright pour extraire les liens depuis une page de recherche."""
    from playwright.sync_api import sync_playwright

    urls: list[str] = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="load", timeout=25000)
            time.sleep(2)
            links = page.query_selector_all("a[href*='/fr/companies/'][href*='/jobs/']")
            for link in links:
                href = link.get_attribute("href")
                if not href:
                    continue
                path = href.split("?")[0].rstrip("/")
                if path.endswith("/jobs"):
                    continue
                if "/fr/pages/" in href:
                    continue
                if "/jobs/" not in path:
                    continue
                full = "https://www.welcometothejungle.com" + href if href.startswith("/") else href
                if full not in urls:
                    urls.append(full)
                if len(urls) >= max_jobs:
                    break
            browser.close()
        except Exception as e:
            print(f"[search_extract] WTTJ {url[:60]} : {e}")
    return urls


def _extract_from_page_generic(url: str, max_jobs: int, selectors: list[str], base: str, filter_fn=lambda h: True) -> list[str]:
    """Extracteur générique requests + BeautifulSoup."""
    urls: list[str] = []
    seen: set[str] = set()
    try:
        time.sleep(random.uniform(2, 4))
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for sel in selectors:
            for a in soup.select(sel):
                href = a.get("href", "")
                if not href or href in seen:
                    continue
                if not filter_fn(href):
                    continue
                full = base + href if href.startswith("/") else (href if href.startswith("http") else base + href)
                if full not in seen:
                    seen.add(href)
                    urls.append(full)
                if len(urls) >= max_jobs:
                    return urls
    except Exception as e:
        print(f"[search_extract] Generic {url[:60]} : {e}")
    return urls


def extract_job_urls_from_search_page(url: str, max_jobs: int = 15) -> list[str]:
    """
    Extrait les URLs d'annonces individuelles depuis une page de recherche (URL fournie par l'utilisateur).
    Retourne [] si l'URL n'est pas une page de recherche connue ou en cas d'erreur.
    """
    u = url.lower()
    if "glassdoor" in u:
        return _extract_from_page_glassdoor(url, max_jobs)
    if "indeed" in u:
        return _extract_from_page_indeed(url, max_jobs)
    if "francetravail" in u:
        return _extract_from_page_francetravail(url, max_jobs)
    if "welcometothejungle" in u:
        return _extract_from_page_wttj(url, max_jobs)
    if "hellowork" in u:
        return _extract_from_page_generic(
            url, max_jobs,
            ["a[href*='/emplois/']"],
            SOURCES["hellowork"]["base"],
            lambda h: "/emplois/" in h and ".html" in h
        )
    if "meteojob" in u:
        return _extract_from_page_generic(
            url, max_jobs,
            ["a[href*='/emploi/'], a[href*='/Emploi/'], a[href*='/job/']"],
            SOURCES["meteojob"]["base"],
            lambda h: not h.startswith("http") or "meteojob.com" in h
        )
    if "chooseyourboss" in u:
        return _extract_from_page_generic(
            url, max_jobs,
            ["a[href*='/candidates/offers/']"],
            SOURCES["chooseyourboss"]["base"],
            lambda h: True
        )
    if "apec" in u:
        return _extract_from_page_generic(
            url, max_jobs,
            ["a[href*='/detail-offre/']"],
            SOURCES["apec"]["base"],
            lambda h: True
        )
    if "manpower" in u:
        return _extract_from_page_generic(
            url, max_jobs,
            ["a[href*='/offre-emploi/'], a[href*='/job/']"],
            SOURCES["manpower"]["base"],
            lambda h: "keywords=" not in h and "offre-emploi?" not in h
        )
    if "adecco" in u:
        return _extract_from_page_generic(
            url, max_jobs,
            ["a[href*='/offre/'], a[href*='/emploi/']"],
            SOURCES["adecco"]["base"],
            lambda h: "recherche" not in h
        )
    if "dogfinance" in u:
        return _extract_from_page_generic(
            url, max_jobs,
            ["a[href*='/offres/'], a[href*='/offre/']"],
            "https://dogfinance.com",
            lambda h: "offres?" not in h and "page=" not in h
        )
    if "linkedin" in u:
        return _extract_from_page_generic(
            url, max_jobs,
            ["a[href*='/jobs/view/'], a[href*='/job/']"],
            SOURCES["linkedin"]["base"],
            lambda h: "linkedin.com" in (h if h.startswith("http") else "") and "/jobs/view/" in h
        )
    return []


def discover_jobs(
    source: str,
    max_jobs: int = 10,
    base_json: dict | None = None,
) -> list[str]:
    """
    Retourne une liste d'URLs d'offres individuelles.
    Si base_json fourni : requêtes dérivées des personas (persona_queries).
    Sinon : requêtes SOURCES par défaut.
    WTTJ : Playwright (SPA React). France Travail : requests.
    """
    from scheduler.persona_queries import get_persona_queries

    source = source.strip().lower()
    config = SOURCES.get(source)
    if not config:
        raise ValueError(f"Source inconnue : {source}")

    queries = (
        get_persona_queries(base_json, max_per_persona=3)
        if base_json
        else config.get("queries", ["python"])
    )

    if source == "wttj":
        all_urls: list[str] = []
        seen: set[str] = set()
        for query in queries:
            if len(all_urls) >= max_jobs:
                break
            time.sleep(random.uniform(2, 5))
            batch = _discover_jobs_wttj_playwright(query, max_jobs - len(all_urls))
            for u in batch:
                if u not in seen:
                    seen.add(u)
                    all_urls.append(u)
        return all_urls[:max_jobs]

    if source == "francetravail":
        return _discover_jobs_francetravail(max_jobs, base_json)

    if source == "indeed":
        return _discover_jobs_indeed(max_jobs, base_json)

    if source == "chooseyourboss":
        return _discover_jobs_chooseyourboss(max_jobs, base_json)

    if source == "hellowork":
        return _discover_jobs_hellowork(max_jobs, base_json)

    if source == "dogfinance":
        return _discover_jobs_dogfinance(max_jobs, base_json)

    if source == "meteojob":
        return _discover_jobs_meteojob(max_jobs, base_json)

    if source == "glassdoor":
        return _discover_jobs_glassdoor(max_jobs, base_json)

    if source == "linkedin":
        return _discover_jobs_linkedin(max_jobs, base_json)

    if source == "apec":
        return _discover_jobs_apec(max_jobs, base_json)

    if source == "manpower":
        return _discover_jobs_manpower(max_jobs, base_json)

    if source == "adecco":
        return _discover_jobs_adecco(max_jobs, base_json)

    return []
