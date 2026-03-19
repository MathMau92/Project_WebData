"""
Étape 1B — Enrichissement des titres via l'API RAWG
Input  : data/titles.json   (généré par step1_get_titles.py)
Output : data/raw/all_games.json

Prérequis :
    pip install requests
    Clé API gratuite sur https://rawg.io/apidocs

Lance :
    python step2_enrich_rawg.py
"""

import json
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# ⚠️  Mets ta clé API RAWG ici (gratuit sur https://rawg.io/apidocs)
# ---------------------------------------------------------------------------
API_KEY = "cd0014ae3d814377b580e3ee935e8ce7"

# ---------------------------------------------------------------------------

RAWG_URL    = "https://api.rawg.io/api"
HEADERS     = {"User-Agent": "ProjetEtudiantWebDatamining (mathieu.maury@edu.devinci.fr)"}
CRAWL_DELAY = 0.05

INPUT_FILE  = Path("data/titles.json")
OUTPUT_FILE = Path("data/raw/all_games.json")

# ---------------------------------------------------------------------------

def search_game(title: str) -> dict | None:
    """Cherche un jeu par titre sur RAWG, retourne le meilleur résultat."""
    params = {
        "key":       API_KEY,
        "search":    title,
        "page_size": 1,
    }
    try:
        resp = requests.get(f"{RAWG_URL}/games", params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return results[0] if results else None
    except Exception as e:
        print(f"  [ERREUR recherche] {e}")
        return None


def get_game_details(game_id: int) -> dict | None:
    """Récupère les détails complets (développeurs, éditeurs, description)."""
    params = {"key": API_KEY}
    try:
        resp = requests.get(f"{RAWG_URL}/games/{game_id}", params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  [ERREUR détails] {e}")
        return None


def parse_game(raw: dict, original_title: str) -> dict:
    """Transforme la réponse RAWG en dict propre."""
    import re

    genres     = ", ".join(g["name"] for g in raw.get("genres", []))
    platforms  = ", ".join(p["platform"]["name"] for p in raw.get("platforms", [])) if raw.get("platforms") else ""
    developers = ", ".join(d["name"] for d in raw.get("developers", []))
    publishers = ", ".join(p["name"] for p in raw.get("publishers", []))
    tags       = ", ".join(t["name"] for t in raw.get("tags", [])[:5])

    desc = raw.get("description_raw") or raw.get("description", "")
    desc = re.sub(r"<[^>]+>", "", desc)
    desc = re.sub(r"\s{2,}", " ", desc).strip()[:500]

    return {
        "titre_original": original_title,           # titre Wikipedia FR
        "titre_rawg":     raw.get("name", ""),       # titre RAWG (peut différer)
        "rawg_id":        raw.get("id"),
        "type":           "Jeu",
        "genre":          genres,
        "développeur":    developers,
        "éditeur":        publishers,
        "plateforme":     platforms,
        "date_sortie":    (raw.get("released") or "")[:4],
        "note":           raw.get("rating", ""),
        "metacritic":     raw.get("metacritic", ""),
        "tags":           tags,
        "site_web":       raw.get("website", ""),
        "texte_intro":    desc,
    }


def main():
    if API_KEY == "Mets":
        print("❌ Mets ta clé API dans API_KEY !")
        print("   → Inscris-toi sur https://rawg.io/apidocs (gratuit)")
        return

    if not INPUT_FILE.exists():
        print(f"❌ Fichier introuvable : {INPUT_FILE}")
        print("   → Lance d'abord step1_get_titles.py")
        return

    titles = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    print(f"=== {len(titles)} titres à enrichir ===\n")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    results  = []
    not_found = []

    for i, title in enumerate(titles, 1):
        print(f"[{i}/{len(titles)}] {title}", end=" ")

        # 1. Chercher le jeu
        stub = search_game(title)
        if not stub:
            print("✗ non trouvé")
            not_found.append(title)
            time.sleep(CRAWL_DELAY)
            continue

        # 2. Récupérer les détails complets
        details = get_game_details(stub["id"])
        if not details:
            print("✗ détails manquants")
            not_found.append(title)
            time.sleep(CRAWL_DELAY)
            continue

        game = parse_game(details, original_title=title)
        results.append(game)
        print(f"✓  →  {game['titre_rawg']} ({game['date_sortie']})")
        time.sleep(CRAWL_DELAY)

    # Sauvegarde
    OUTPUT_FILE.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"\n=== Terminé ===")
    print(f"  Trouvés   : {len(results)}")
    print(f"  Non trouvés : {len(not_found)}")
    print(f"  Fichier   : {OUTPUT_FILE}")

    if not_found:
        print(f"\nTitres non trouvés sur RAWG :")
        for t in not_found[:10]:
            print(f"  - {t}")

    # Exemple
    if results:
        print("\nExemple de jeu enrichi :")
        for k, v in results[0].items():
            if v:
                print(f"  {k:<18} {str(v)[:70]}")


if __name__ == "__main__":
    main()