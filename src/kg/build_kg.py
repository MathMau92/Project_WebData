"""
Étape 2 — Construction du Graphe RDF
Input  : data/raw/all_games.json  (généré par step2_enrich_rawg.py)
Output : kg_artifacts/videogames.ttl

Installe :
    pip install rdflib

Lance :
    python step3_build_kg.py
"""

import json
import re
from pathlib import Path

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

# ---------------------------------------------------------------------------
# Namespaces
# ---------------------------------------------------------------------------

VG   = Namespace("http://videogamekg.org/ontology#")
ENT  = Namespace("http://videogamekg.org/entity/")
SCH  = Namespace("https://schema.org/")

# ---------------------------------------------------------------------------
# Chemins
# ---------------------------------------------------------------------------

INPUT_FILE  = Path("data/raw/all_games.json")
OUTPUT_DIR  = Path("kg_artifacts")
OUTPUT_FILE = OUTPUT_DIR / "ontology.ttl"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """
    Transforme un nom en URI valide et STABLE.
    'EightyEight Games' et 'EightyEightGames' → même URI 'EightyEight_Games'
    """
    s = str(text).strip()
    # Normalisation : insérer un espace avant les majuscules collées (CamelCase)
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    # Remplacer tout ce qui n'est pas alphanumérique par _
    s = re.sub(r"[^\w]", "_", s)
    # Supprimer les _ multiples
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:80]

def uri(name: str) -> URIRef:
    return ENT[slugify(name)]

def split_values(text: str) -> list[str]:
    """Découpe 'Action, RPG, Adventure' en liste propre."""
    return [v.strip() for v in re.split(r"[,;]", text) if v.strip()]

# ---------------------------------------------------------------------------
# Ontologie (TBox) — classes et propriétés
# ---------------------------------------------------------------------------

def build_ontology(g: Graph) -> None:

    # -- Classes --
    classes = {
        VG.Game:      "Video Game",
        VG.Studio:    "Game Studio",
        VG.Publisher: "Game Publisher",
        VG.Genre:     "Game Genre",
        VG.Platform:  "Gaming Platform",
    }
    for cls, label in classes.items():
        g.add((cls, RDF.type,   OWL.Class))
        g.add((cls, RDFS.label, Literal(label, lang="en")))

    # -- Propriétés objet --
    obj_props = [
        (VG.developedBy,  VG.Game,    VG.Studio,    "developed by"),
        (VG.publishedBy,  VG.Game,    VG.Publisher, "published by"),
        (VG.hasGenre,     VG.Game,    VG.Genre,     "has genre"),
        (VG.availableOn,  VG.Game,    VG.Platform,  "available on"),
    ]
    for prop, domain, range_, label in obj_props:
        g.add((prop, RDF.type,      OWL.ObjectProperty))
        g.add((prop, RDFS.domain,   domain))
        g.add((prop, RDFS.range,    range_))
        g.add((prop, RDFS.label,    Literal(label, lang="en")))

    # -- Propriétés datatype --
    data_props = [
        (VG.releaseYear, XSD.integer, "release year"),
        (VG.rating,      XSD.float,   "average rating"),
        (VG.metacritic,  XSD.integer, "metacritic score"),
        (VG.website,     XSD.anyURI,  "official website"),
        (VG.description, XSD.string,  "description"),
        (VG.rawgId,      XSD.integer, "RAWG identifier"),
    ]
    for prop, datatype, label in data_props:
        g.add((prop, RDF.type,    OWL.DatatypeProperty))
        g.add((prop, RDFS.range,  datatype))
        g.add((prop, RDFS.label,  Literal(label, lang="en")))

    # Alignements externes (Schema.org)
    g.add((VG.Game,       OWL.equivalentClass,    SCH.VideoGame))
    g.add((VG.developedBy, OWL.equivalentProperty, SCH.author))
    g.add((VG.hasGenre,   OWL.equivalentProperty, SCH.genre))

    # Propriétés d'expansion (ajoutées ici pour qu'elles soient dans le TBox)
    for prop, label in [
        (VG.sameStudioAs, "developed by same studio"),
        (VG.similarTo,    "similar game"),
    ]:
        g.add((prop, RDF.type,    OWL.SymmetricProperty))
        g.add((prop, RDFS.label,  Literal(label, lang="en")))
        g.add((prop, RDFS.domain, VG.Game))
        g.add((prop, RDFS.range,  VG.Game))

# ---------------------------------------------------------------------------
# Population (ABox) — une entrée JSON → triplets RDF
# ---------------------------------------------------------------------------

def add_game(g: Graph, game: dict) -> None:
    titre = game.get("titre_rawg") or game.get("titre_original", "")
    if not titre:
        return

    game_uri = uri(titre)
    g.add((game_uri, RDF.type,   VG.Game))
    g.add((game_uri, RDFS.label, Literal(titre, lang="en")))

    # Titre original FR — seulement si vraiment proche du titre RAWG
    # (évite les faux matchs Wikipedia → RAWG)
    titre_fr = game.get("titre_original", "")
    if titre_fr and titre_fr != titre:
        # Vérification simple : au moins 3 mots en commun ou ratio de similarité
        words_en = set(titre.lower().split())
        words_fr = set(titre_fr.lower().split())
        common   = words_en & words_fr
        if len(common) >= 2 or any(w in titre.lower() for w in words_fr if len(w) > 4):
            g.add((game_uri, RDFS.label, Literal(titre_fr, lang="fr")))

    # Propriétés datatype
    if game.get("date_sortie"):
        try:
            g.add((game_uri, VG.releaseYear, Literal(int(game["date_sortie"]), datatype=XSD.integer)))
        except ValueError:
            pass

    if game.get("note"):
        try:
            g.add((game_uri, VG.rating, Literal(float(game["note"]), datatype=XSD.float)))
        except (ValueError, TypeError):
            pass

    if game.get("metacritic"):
        try:
            g.add((game_uri, VG.metacritic, Literal(int(game["metacritic"]), datatype=XSD.integer)))
        except (ValueError, TypeError):
            pass

    if game.get("site_web"):
        g.add((game_uri, VG.website, Literal(game["site_web"], datatype=XSD.anyURI)))

    if game.get("texte_intro"):
        g.add((game_uri, VG.description, Literal(game["texte_intro"][:300], lang="en")))

    if game.get("rawg_id"):
        g.add((game_uri, VG.rawgId, Literal(int(game["rawg_id"]), datatype=XSD.integer)))

    # Développeurs
    for dev in split_values(game.get("développeur", "")):
        dev_uri = uri(dev)
        g.add((dev_uri, RDF.type,   VG.Studio))
        g.add((dev_uri, RDFS.label, Literal(dev, lang="en")))
        g.add((game_uri, VG.developedBy, dev_uri))

    # Éditeurs
    for pub in split_values(game.get("éditeur", "")):
        pub_uri = uri(pub)
        g.add((pub_uri, RDF.type,   VG.Publisher))
        g.add((pub_uri, RDFS.label, Literal(pub, lang="en")))
        g.add((game_uri, VG.publishedBy, pub_uri))

    # Genres
    for genre in split_values(game.get("genre", "")):
        genre_uri = uri(genre)
        g.add((genre_uri, RDF.type,   VG.Genre))
        g.add((genre_uri, RDFS.label, Literal(genre, lang="en")))
        g.add((game_uri, VG.hasGenre, genre_uri))

    # Plateformes
    for platform in split_values(game.get("plateforme", "")):
        plat_uri = uri(platform)
        g.add((plat_uri, RDF.type,   VG.Platform))
        g.add((plat_uri, RDFS.label, Literal(platform, lang="en")))
        g.add((game_uri, VG.availableOn, plat_uri))

# ---------------------------------------------------------------------------
# Extension SPARQL — inférer des triplets supplémentaires
# ---------------------------------------------------------------------------

EXPANSION_QUERIES = {
    # Si un studio développe ET publie un jeu → le marquer aussi comme publisher
    "studio_est_aussi_publisher": """
        PREFIX vg: <http://videogamekg.org/ontology#>
        CONSTRUCT { ?e a vg:Publisher . }
        WHERE {
            ?e a vg:Studio .
            ?game vg:publishedBy ?e .
        }
    """,
    # Jeux du même développeur → liés par sameStudio (plus utile que sameGenre)
    "meme_studio": """
        PREFIX vg: <http://videogamekg.org/ontology#>
        CONSTRUCT { ?g1 vg:sameStudioAs ?g2 . }
        WHERE {
            ?g1 vg:developedBy ?studio .
            ?g2 vg:developedBy ?studio .
            FILTER(?g1 != ?g2)
            FILTER(STR(?g1) < STR(?g2))
        }
    """,
    # Jeux sur la même plateforme et même genre → recommandation potentielle
    "meme_plateforme_genre": """
        PREFIX vg: <http://videogamekg.org/ontology#>
        CONSTRUCT { ?g1 vg:similarTo ?g2 . }
        WHERE {
            ?g1 vg:hasGenre    ?genre .
            ?g1 vg:availableOn ?platform .
            ?g2 vg:hasGenre    ?genre .
            ?g2 vg:availableOn ?platform .
            FILTER(?g1 != ?g2)
            FILTER(STR(?g1) < STR(?g2))
        }
    """,
}

def expand_graph(g: Graph) -> int:
    added = 0
    for name, query in EXPANSION_QUERIES.items():
        try:
            new_triples = list(g.query(query))
            for triple in new_triples:
                g.add(triple)
            print(f"  Expansion '{name}' : +{len(new_triples)} triplets")
            added += len(new_triples)
        except Exception as e:
            print(f"  [WARN] Expansion '{name}' ignorée : {e}")

    return added

# ---------------------------------------------------------------------------
# Statistiques
# ---------------------------------------------------------------------------

def print_stats(g: Graph) -> None:
    print("\n── Statistiques du graphe ──────────────────")
    print(f"Total triplets : {len(g)}")

    q = """
        SELECT ?class (COUNT(?s) AS ?n) WHERE {
            ?s a ?class .
        } GROUP BY ?class ORDER BY DESC(?n)
    """
    print("\nEntités par classe :")
    for row in g.query(q):
        cls = str(row[0]).split("#")[-1].split("/")[-1]
        print(f"  {cls:<20} {int(row[1])}")

    q2 = """
        SELECT ?p (COUNT(*) AS ?n) WHERE { ?s ?p ?o . }
        GROUP BY ?p ORDER BY DESC(?n) LIMIT 8
    """
    print("\nTop prédicats :")
    for row in g.query(q2):
        pred = str(row[0]).split("#")[-1].split("/")[-1]
        print(f"  {pred:<25} {int(row[1])}")
    print("────────────────────────────────────────────\n")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not INPUT_FILE.exists():
        print(f" Fichier introuvable : {INPUT_FILE}")
        print("   → Lance d'abord step1 et step2")
        return

    games = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    print(f"=== {len(games)} jeux chargés depuis {INPUT_FILE} ===\n")

    g = Graph()
    g.bind("vg",   VG)
    g.bind("ent",  ENT)
    g.bind("sch",  SCH)
    g.bind("owl",  OWL)
    g.bind("rdfs", RDFS)

    # TBox
    build_ontology(g)
    print("Ontologie construite.")

    # ABox
    for game in games:
        add_game(g, game)
    print(f"ABox peuplée : {len(g)} triplets avant expansion.")

    # Extension SPARQL
    print("\nExtension SPARQL :")
    added = expand_graph(g)
    print(f"Total après expansion : {len(g)} triplets (+{added})")

    # Sauvegarde
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    g.serialize(destination=str(OUTPUT_FILE), format="turtle")
    print(f"\nGraphe sauvegardé → {OUTPUT_FILE}")

    print_stats(g)


if __name__ == "__main__":
    main()