"""
Étape 1A — Récupération des titres de jeux vidéo (Wikipedia FR)
Output : data/titles.json  →  liste de titres bruts

Lance :
    python step1_get_titles.py
"""

import json
import re
import time
from pathlib import Path

import requests

API_URL     = "https://fr.wikipedia.org/w/api.php"
HEADERS     = {"User-Agent": "ProjetEtudiantWebDatamining (mathieu.maury@edu.devinci.fr)"}
CRAWL_DELAY = 0.05
MAX_TITLES  = 50

SEED_CATEGORIES = [
    "Jeu vidéo de rôle",
    "Jeu d'action-aventure",
    "Jeu de tir à la première personne",
    "Jeu vidéo de stratégie",
    "Liste de jeux vidéo basés sur les Jeux olympiques",
    "Jeu vidéo indépendant",
    "Jeu vidéo de football",
    "Jeu vidéo de boxe",
    "Liste de jeux vidéo de volley-ball",
    "Liste de jeux vidéo de basket-ball",
    "Action-RPG",
]

# Préfixes à exclure (méta-pages Wikipedia)
EXCLUDED_PREFIXES = (
    "liste ", "jeu vidéo de ", "jeu vidéo d'",
    "développeur", "éditeur", "portail",
    "catégorie", "modèle", "wikipédia",
)

OUTPUT_FILE = Path("data/titles.json")

# ---------------------------------------------------------------------------

def get_category_members(category_name: str, limit: int = 50) -> list[str]:
    params = {
        "action":      "query",
        "list":        "categorymembers",
        "cmtitle":     f"Catégorie:{category_name}",
        "cmlimit":     limit,
        "cmnamespace": 0,
        "format":      "json",
    }
    titles = []
    while True:
        try:
            data = requests.get(API_URL, params=params, headers=HEADERS, timeout=10).json()
        except Exception as e:
            print(f"  [ERREUR] {e}")
            break

        items = data.get("query", {}).get("categorymembers", [])
        if not items:
            print(f"  [VIDE] '{category_name}'")
            break

        for m in items:
            title = m["title"]
            if not any(title.lower().startswith(p) for p in EXCLUDED_PREFIXES):
                # Nettoyer les suffixes "(jeu vidéo)" ou "(jeu vidéo, 1984)"
                clean = re.sub(r"\s*\(jeu vidéo[^)]*\)", "", title).strip()
                titles.append(clean)

        cont = data.get("continue", {}).get("cmcontinue")
        if cont and len(titles) < limit:
            params["cmcontinue"] = cont
            time.sleep(0.3)
        else:
            break

    return titles


def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    print("=== Collecte des titres via Wikipedia FR ===")
    seen   = set()
    titles = []

    for cat in SEED_CATEGORIES:
        new_titles = get_category_members(cat, limit=60)
        new = [t for t in new_titles if t not in seen]
        seen.update(new)
        titles.extend(new)
        print(f"  '{cat}' → {len(new_titles)} trouvés, {len(new)} nouveaux")
        time.sleep(CRAWL_DELAY)

    titles = titles[:MAX_TITLES]

    OUTPUT_FILE.write_text(
        json.dumps(titles, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"\n=== Terminé : {len(titles)} titres → {OUTPUT_FILE} ===")
    print("\nExemples :")
    for t in titles[:10]:
        print(f"  - {t}")


if __name__ == "__main__":
    main()