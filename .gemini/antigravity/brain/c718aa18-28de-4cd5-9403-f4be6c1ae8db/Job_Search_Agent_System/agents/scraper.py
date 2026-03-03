"""
Agent Scraper - Extraction structurée des offres d'emploi via LLM.
"""
import requests
import re
import json
from bs4 import BeautifulSoup
from core.models import ScraperOutput
from core.llm_client import OpenAIClient

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}


class ScraperOffre:
    def __init__(self):
        self.llm = OpenAIClient()

    def clean_html(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for script in soup(["script", "style"]):
            script.extract()
        text = soup.get_text(separator=" ")
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        return " ".join(chunk for chunk in chunks if chunk)

    def extract_with_llm(self, url: str, clean_text: str) -> ScraperOutput:
        prompt = f"""
Analyse cette offre d'emploi et extrait les briques suivantes en JSON :
- titre : intitulé exact du poste.
- entreprise : nom de la société.
- description_clean : résumé des points clés de l'offre (200 mots max).
- mots_cles_detectes : liste des 8-12 compétences techniques, outils (ex: GA4, Django, GLPI) ou métiers mentionnés.
- niveau_poste : junior, intermediaire, senior ou strategique (basé sur l'expérience demandée : <2 ans=junior, 2-5=intermediaire, 5-8=senior, >8 ou Manager=strategique).
- probleme_detecte : Quel est le défi principal que ce recrutement doit relever ?

Texte de l'offre :
{clean_text[:5000]}
"""
        
        try:
            res = self.llm.chat_completion(prompt, system_prompt="Tu es un extracteur de données RH précis.", json_mode=True)
            if not isinstance(res, dict):
                raise ValueError("Réponse LLM non-dict")
            return ScraperOutput(**res)
        except Exception as e:
            print(f"Erreur d'extraction LLM: {e}")
            return ScraperOutput(
                titre="Poste Inconnu",
                entreprise="Entreprise Inconnue",
                description_clean="Erreur lors de l'extraction des détails.",
                mots_cles_detectes=[],
                niveau_poste="Intermediaire",
                probleme_detecte="N/A"
            )

    def process(self, url: str) -> ScraperOutput:
        fallback = ScraperOutput(
            titre="Poste Inconnu",
            entreprise="Entreprise Inconnue",
            description_clean="Contenu inaccessible (erreur HTTP).",
            mots_cles_detectes=[],
            niveau_poste="Intermediaire",
            probleme_detecte="N/A",
        )
        try:
            response = requests.get(url, headers=HEADERS, timeout=20)
            response.raise_for_status()
            clean_text = self.clean_html(response.text)
        except requests.HTTPError as e:
            print(f"Erreur scraping URL {url}: {e}")
            return fallback
        except Exception as e:
            print(f"Erreur scraping URL {url}: {e}")
            return fallback
        if not clean_text or len(clean_text.strip()) < 50:
            return fallback
        return self.extract_with_llm(url, clean_text)

class EntrepriseScraper:
    def process(self, url: str) -> dict:
        return {
            "email_trouve": None,
            "niveau_confiance": "Basse",
            "source": "Scraping standard"
        }
