"""
Script final corrigé pour Orange Travel avec support UTF-8.
"""
import os
import sys
import json
import io

# Forcer la sortie standard en UTF-8 pour Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Ajout du chemin racine pour l'import des agents
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.orchestrator import Orchestrator
from core.models import ScraperOutput

def main():
    base_json_path = os.path.join('resources', 'base_real.json')
    if not os.path.exists(base_json_path):
        print(f"Erreur: {base_json_path} introuvable.")
        return

    with open(base_json_path, 'r', encoding='utf-8') as f:
        base_json = json.load(f)

    orange_job_data = ScraperOutput(
        titre="Responsable SEO (F/H)",
        entreprise="Orange Travel",
        description_clean="""Orange Travel recherche son futur Responsable SEO pour piloter la stratégie internationale. 
        Missions : Audits techniques, crawl, indexation, vitals, stratégie éditoriale, gestion de backlinks, reporting GA4/GTM. 
        Expertise IA (AI Overviews, Perplexity) souhaitée. 5 ans d'expérience minimum. 
        Outils : Screaming Frog, GSC, Ahrefs, SEMRush.""",
        mots_cles_detectes=["SEO technique", "IA", "GA4", "Screaming Frog", "Stratégie éditoriale", "Backlinks"],
        niveau_poste="Strategique",
        probleme_detecte="Internalisation de l'expertise SEO et optimisation de la visibilité sur les nouveaux moteurs IA."
    )

    orchestrator = Orchestrator(base_json=base_json)
    
    orchestrator.scraper.process = lambda url: orange_job_data
    orchestrator.entreprise_scraper.process = lambda url: {
        "email_trouve": "contact@travel-orange.com",
        "niveau_confiance": "Haute",
        "source": "Recherche manuelle"
    }

    print("Lancement de la campagne agentique avec API GPT (OpenAI)...")
    report = orchestrator.run_pipeline("https://orange.jobs/jobs/offer/135965", create_draft=True)

    print("\n--- RAPPORT FINAL GÉNÉRÉ PAR AGENT ---")
    # Sérialisation propre avec ensure_ascii=False
    print(json.dumps(report.model_dump(), indent=2, ensure_ascii=False))
    
    print("\nMission accomplie : Brouillon Gmail créé avec CV et LM adaptés !")

if __name__ == '__main__':
    main()
