"""
Étape 3 — Raisonnement SWRL avec owlready2 + Pellet
Partie A : family.owl
Partie B : graphe jeux vidéo (construit depuis data/raw/all_games.json)

Prérequis :
    pip install owlready2
    Java 17+

Lance :
    python src/reason/reasoning.py
"""

import json
import os
import re
from pathlib import Path
from owlready2 import *

# ---------------------------------------------------------------------------
# Chemins
# ---------------------------------------------------------------------------

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

FAMILY_OWL   = Path(PROJECT_ROOT) / "data" / "family.owl"
GAMES_JSON   = Path(PROJECT_ROOT) / "data" / "raw" / "all_games.json"
OUTPUT_DIR   = Path(PROJECT_ROOT) / "kg_artifacts"

FAM = "http://www.owl-ontologies.com/unnamed.owl#"
VG  = "http://videogamekg.org/swrl/"

# ---------------------------------------------------------------------------
# Utilitaire
# ---------------------------------------------------------------------------

def slugify(s: str) -> str:
    return re.sub(r"[^\w]", "_", str(s).strip())[:60]

def n(entity) -> str:
    if hasattr(entity, "label") and entity.label:
        return str(entity.label[0])
    return str(entity.iri).split("#")[-1].split("/")[-1]

# ---------------------------------------------------------------------------
# PARTIE A — family.owl + Pellet
# ---------------------------------------------------------------------------

def run_family():
    print("=" * 55)
    print("PARTIE A — family.owl (owlready2 + Pellet)")
    print("=" * 55)

    if not FAMILY_OWL.exists():
        print(f"  Fichier introuvable : {FAMILY_OWL}")
        return

    onto = get_ontology(FAM)
    with open(FAMILY_OWL, "rb") as f:
        onto.load(fileobj=f)
    print(f"\nOntologie chargée : {onto.base_iri}")

    with onto:
        class hasGrandParent(onto.Person >> onto.Person): namespace = onto

        # Règle unique : isChildOf(?x,?y) ∧ isChildOf(?y,?z) → hasGrandParent(?x,?z)
        Imp().set_as_rule(
            "isChildOf(?x,?y), isChildOf(?y,?z), differentFrom(?x,?z)"
            " -> hasGrandParent(?x,?z)"
        )

    print("\nLancement de Pellet...")
    with onto:
        sync_reasoner_pellet(infer_property_values=True)
    print("Inférence terminée.\n")

    print("── Résultats ──────────────────────────────────")

    print("\n[Règle] Grands-parents inférés :")
    for x, z in default_world.sparql(
        f"SELECT ?x ?z WHERE {{ ?x <{FAM}hasGrandParent> ?z . }}"
    ):
        print(f"  {n(x)}.hasGrandParent → {n(z)}")

    print("""
── Règle SWRL appliquée ───────────────────────
  isChildOf(?x,?y) ∧ isChildOf(?y,?z) → hasGrandParent(?x,?z)
────────────────────────────────────────────────""")


# ---------------------------------------------------------------------------
# PARTIE B — Jeux Vidéo depuis all_games.json + Pellet
#
# On construit l'ontologie directement en Python depuis le JSON
# pour éviter les owl:equivalentProperty (schema.org) qui rendent
# ontology.ttl inconsistant pour Pellet.
# ---------------------------------------------------------------------------

def run_videogames():
    print("\n" + "=" * 55)
    print("PARTIE B — Jeux Vidéo (owlready2 + Pellet)")
    print("=" * 55)

    if not GAMES_JSON.exists():
        print(f"  Fichier introuvable : {GAMES_JSON}")
        return

    games = json.loads(GAMES_JSON.read_text(encoding="utf-8"))
    print(f"\n{len(games)} jeux chargés depuis {GAMES_JSON}")

    onto = get_ontology(VG)

    with onto:
        class Game(Thing):   pass
        class Studio(Thing): pass
        class Genre(Thing):  pass

        class developedBy(Game >> Studio):     pass
        class publishedBy(Game >> Studio):     pass
        class hasGenre(Game >> Genre):         pass
        class isSelfPublished(Game >> Studio): pass
        class recommendedWith(Game >> Game):   pass

        studio_cache: dict = {}
        genre_cache:  dict = {}

        def get_studio(name: str) -> Studio:
            slug = slugify(name)
            if slug not in studio_cache:
                s = Studio(slug, namespace=onto)
                s.label = [name]
                studio_cache[slug] = s
            return studio_cache[slug]

        def get_genre(name: str) -> Genre:
            slug = slugify(name)
            if slug not in genre_cache:
                g = Genre(slug, namespace=onto)
                g.label = [name]
                genre_cache[slug] = g
            return genre_cache[slug]

        game_objs: dict = {}
        for entry in games:
            titre = entry.get("titre_rawg") or entry.get("titre_original", "")
            if not titre:
                continue
            slug = slugify(titre)
            obj = Game(slug, namespace=onto)
            obj.label = [titre]
            game_objs[slug] = obj

            devs   = [v.strip() for v in str(entry.get("développeur","")).split(",") if v.strip()]
            pubs   = [v.strip() for v in str(entry.get("éditeur","")).split(",") if v.strip()]
            genres = [v.strip() for v in str(entry.get("genre","")).split(",") if v.strip()]

            obj.developedBy = [get_studio(d) for d in devs]
            obj.publishedBy = [get_studio(p) for p in pubs]
            obj.hasGenre    = [get_genre(g) for g in genres]

        print(f"{len(game_objs)} jeux, {len(studio_cache)} studios, {len(genre_cache)} genres créés")

        # R1 : developedBy(?g,?s) ∧ publishedBy(?g,?s) → isSelfPublished(?g,?s)
        Imp().set_as_rule(
            "Game(?g), developedBy(?g,?s), publishedBy(?g,?s)"
            " -> isSelfPublished(?g,?s)"
        )

        # R2 : metacritic(?g,?n) ∧ swrlb:greaterThan(?n,80) → isAAA(?g)
        # owlready2/Pellet ne supporte pas swrlb:greaterThan sur des datatype,
        # on applique cette règle après l inférence via un post-traitement Python
        class isAAA(Game >> str): namespace = onto
        class metacritic(Game >> int): namespace = onto

        # On peuple metacritic depuis le JSON
        for entry in games:
            titre = entry.get("titre_rawg") or entry.get("titre_original", "")
            if not titre:
                continue
            slug = slugify(titre)
            score = entry.get("metacritic")
            if score and slug in game_objs:
                game_objs[slug].metacritic = [int(score)]

    print("\nLancement de Pellet...")
    with onto:
        sync_reasoner_pellet(infer_property_values=True)
    print("Inférence terminée.\n")

    print("── Résultats ──────────────────────────────────")

    # Post-traitement R2 : isAAA (swrlb:greaterThan non supporté par Pellet sur datatype)
    aaa_games = []
    for entry in games:
        score = entry.get("metacritic")
        titre = entry.get("titre_rawg") or entry.get("titre_original", "")
        if score and int(score) > 80 and titre:
            aaa_games.append((titre, int(score)))

    print("\n[R1] Jeux self-published :")
    seen_sp: set = set()
    for x, s in default_world.sparql(
        f"SELECT ?x ?s WHERE {{ ?x <{VG}isSelfPublished> ?s . }}"
    ):
        key = (x.iri, s.iri)
        if key not in seen_sp:
            seen_sp.add(key)
            print(f"  {n(x)}  →  {n(s)}")
    print(f"  Total : {len(seen_sp)}")

    print("\n[R2] Jeux AAA (metacritic > 80) :")
    for titre, score in sorted(aaa_games, key=lambda x: -x[1]):
        print(f"  {titre}  (metacritic: {score})")
    print(f"  Total : {len(aaa_games)}")

    # Sauvegarde
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "swrl_inferred.ttl"
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"@prefix vg: <{VG}> .\n\n")
        for (xi, si) in seen_sp:
            f.write(f"<{xi}> vg:isSelfPublished <{si}> .\n")
        for titre, _ in aaa_games:
            slug = slugify(titre)
            f.write(f"<{VG}{slug}> vg:isAAA \"true\" .\n")
    print(f"\nTriplets inférés sauvegardés → {out}")

    print("""
── Règles SWRL ────────────────────────────────
  R1 : developedBy(?g,?s) ∧ publishedBy(?g,?s) → isSelfPublished(?g,?s)
  R2 : Game(?g) ∧ metacritic(?g,?n) ∧ greaterThan(?n,80) → isAAA(?g)
────────────────────────────────────────────────""")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run_family()
    run_videogames()
    print("\n=== Raisonnement SWRL terminé ===")