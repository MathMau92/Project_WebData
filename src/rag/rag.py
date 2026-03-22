import json
import os
import re
import textwrap
from pathlib import Path

import requests
from rdflib import Graph, Namespace

# ---------------------------------------------------------------------------
# Chemins et config
# ---------------------------------------------------------------------------

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

TTL_FILE      = Path(PROJECT_ROOT) / "kg_artifacts" / "ontology.ttl"
INFERRED_FILE = Path(PROJECT_ROOT) / "kg_artifacts" / "swrl_inferred.ttl"
OLLAMA_URL   = "http://localhost:11434/api/generate"
MODEL        = "llama3.2"
MAX_REPAIRS  = 3   # tentatives de correction de SPARQL

VG  = Namespace("http://videogamekg.org/ontology#")
ENT = Namespace("http://videogamekg.org/entity/")

# ---------------------------------------------------------------------------
# Schéma de l'ontologie (injecté dans le prompt système)
# ---------------------------------------------------------------------------

SCHEMA_SUMMARY = """
You are a SPARQL expert for a video game knowledge graph.

PREFIXES (always include them):
    PREFIX vg:   <http://videogamekg.org/ontology#>
    PREFIX ent:  <http://videogamekg.org/entity/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

CLASSES:
    vg:Game        — a video game
    vg:Studio      — a development studio
    vg:Publisher   — a publisher
    vg:Genre       — a genre
    vg:Platform    — a platform

PROPERTIES (all on vg:Game unless noted):
    rdfs:label         — game name (use FILTER(lang(?l)="en") for English)
    vg:developedBy     → vg:Studio
    vg:publishedBy     → vg:Publisher
    vg:hasGenre        → vg:Genre
    vg:availableOn     → vg:Platform
    vg:sameStudioAs    → vg:Game  (symmetric)
    vg:similarTo       → vg:Game  (symmetric)
    vg:releaseYear     — integer (e.g. 2020)
    vg:rating          — float 0-5
    vg:metacritic      — integer 0-100
    vg:website         — URI

IMPORTANT RULES:
    - Entity URIs use underscores: ent:Assassin_s_Creed_Valhalla
    - Always use rdfs:label with lang filter for readable names
    - Use OPTIONAL for properties that may be missing
    - Limit results with LIMIT 10 unless asked otherwise
    - Output ONLY the SPARQL query, no explanation, no markdown fences

EXAMPLES:

Q: What games were developed by Ubisoft?
A:
PREFIX vg: <http://videogamekg.org/ontology#>
PREFIX ent: <http://videogamekg.org/entity/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?label WHERE {
    ?g a vg:Game ; vg:developedBy ent:Ubisoft ; rdfs:label ?label .
    FILTER(lang(?label)="en")
}

Q: Which RPG games are available on PC?
A:
PREFIX vg: <http://videogamekg.org/ontology#>
PREFIX ent: <http://videogamekg.org/entity/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?label WHERE {
    ?g a vg:Game ;
       vg:hasGenre ent:RPG ;
       vg:availableOn ent:PC ;
       rdfs:label ?label .
    FILTER(lang(?label)="en")
} LIMIT 10

Q: What is the metacritic score of Armello?
A:
PREFIX vg: <http://videogamekg.org/ontology#>
PREFIX ent: <http://videogamekg.org/entity/>
SELECT ?score WHERE {
    ent:Armello vg:metacritic ?score .
}

Q: Which games are similar to Arma 3?
A:
PREFIX vg: <http://videogamekg.org/ontology#>
PREFIX ent: <http://videogamekg.org/entity/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?label WHERE {
    ent:Arma_3 vg:similarTo ?g .
    ?g rdfs:label ?label .
    FILTER(lang(?label)="en")
} LIMIT 10

Q: Which games have a metacritic score above 80?
A:
PREFIX vg: <http://videogamekg.org/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?label ?score WHERE {
    ?g a vg:Game ;
       rdfs:label ?label ;
       vg:metacritic ?score .
    FILTER(lang(?label)="en")
    FILTER(?score > 80)
} ORDER BY DESC(?score)

Q: Which games have a rating above 4?
A:
PREFIX vg: <http://videogamekg.org/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?label ?rating WHERE {
    ?g a vg:Game ;
       rdfs:label ?label ;
       vg:rating ?rating .
    FILTER(lang(?label)="en")
    FILTER(?rating > 4.0)
} ORDER BY DESC(?rating)
"""

# ---------------------------------------------------------------------------
# Chargement du graphe RDF
# ---------------------------------------------------------------------------

def load_graph(ttl_path: Path, inferred_path: Path = None) -> Graph:
    print(f"Chargement du graphe : {ttl_path}")
    g = Graph()
    with open(ttl_path, "rb") as f:
        g.parse(f, format="turtle")
    # Charger aussi les triplets inférés par SWRL si disponibles
    if inferred_path and inferred_path.exists():
        with open(inferred_path, "rb") as f:
            g.parse(f, format="turtle")
        print(f"  + triplets inférés : {inferred_path.name}")
    g.bind("vg",   VG)
    g.bind("ent",  ENT)
    print(f"  {len(g)} triplets chargés au total\n")
    return g

# ---------------------------------------------------------------------------
# Appel Ollama
# ---------------------------------------------------------------------------

def call_ollama(prompt: str, system: str = "") -> str:
    payload = {
        "model":  MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {"temperature": 0.0},  # déterministe pour SPARQL
    }
    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=60)
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except requests.exceptions.ConnectionError:
        return "ERREUR: Ollama n'est pas lancé. Lancez 'ollama serve' dans un terminal."
    except Exception as e:
        return f"ERREUR Ollama: {e}"

# ---------------------------------------------------------------------------
# NL → SPARQL
# ---------------------------------------------------------------------------

def nl_to_sparql(question: str) -> str:
    prompt = f"Convert this question to a SPARQL query:\n\nQ: {question}\nA:"
    raw = call_ollama(prompt, system=SCHEMA_SUMMARY)

    # Nettoyer les balises markdown si le modèle en ajoute
    raw = re.sub(r"```sparql", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"```", "", raw)
    return raw.strip()

# ---------------------------------------------------------------------------
# Exécution SPARQL avec boucle de réparation
# ---------------------------------------------------------------------------

def execute_sparql(g: Graph, query: str) -> tuple[list, str | None]:
    """
    Exécute une requête SPARQL sur le graphe.
    Retourne (résultats, erreur).
    """
    try:
        results = list(g.query(query))
        return results, None
    except Exception as e:
        return [], str(e)


def repair_sparql(question: str, broken_query: str, error: str) -> str:
    """
    Demande au LLM de corriger une requête SPARQL invalide.
    """
    prompt = f"""The following SPARQL query failed with this error:

ERROR: {error}

BROKEN QUERY:
{broken_query}

Fix the query for this question: {question}
Output ONLY the corrected SPARQL query.
"""
    raw = call_ollama(prompt, system=SCHEMA_SUMMARY)
    raw = re.sub(r"```sparql", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"```", "", raw)
    return raw.strip()


def query_with_repair(g: Graph, question: str) -> tuple[list, str, int]:
    """
    Génère une requête SPARQL, l'exécute, et tente de la réparer si elle échoue.
    Retourne (résultats, requête_finale, nb_réparations).
    """
    query = nl_to_sparql(question)
    repairs = 0

    for attempt in range(MAX_REPAIRS + 1):
        results, error = execute_sparql(g, query)
        if error is None:
            return results, query, repairs
        if attempt < MAX_REPAIRS:
            print(f"  [réparation {attempt + 1}/{MAX_REPAIRS}] Erreur : {error[:80]}...")
            query = repair_sparql(question, query, error)
            repairs += 1

    return [], query, repairs

# ---------------------------------------------------------------------------
# Formatage de la réponse finale
# ---------------------------------------------------------------------------

def format_results(results: list) -> str:
    """Convertit les résultats SPARQL en texte lisible."""
    if not results:
        return "(aucun résultat)"
    lines = []
    for row in results:
        parts = [str(v) for v in row if v is not None]
        lines.append("  • " + "  |  ".join(parts))
    return "\n".join(lines)


def generate_answer(question: str, sparql_results: str) -> str:
    """
    Utilise le LLM pour formuler une réponse en langage naturel
    à partir des résultats SPARQL bruts.
    """
    prompt = f"""Based on these results from a video game knowledge graph:

QUESTION: {question}

RESULTS:
{sparql_results}

Write a concise, natural answer in the same language as the question.
If no results, say so clearly.
"""
    return call_ollama(prompt)

# ---------------------------------------------------------------------------
# Pipeline RAG complet
# ---------------------------------------------------------------------------

def rag_pipeline(g: Graph, question: str, verbose: bool = False) -> str:
    """
    Pipeline complet :
    1. NL → SPARQL (via Ollama)
    2. Exécution SPARQL sur le graphe RDF (avec auto-réparation)
    3. Résultats → réponse NL (via Ollama)
    """
    print(f"\n{'─'*55}")
    print(f"Question : {question}")
    print(f"{'─'*55}")

    # Étape 1 : génération SPARQL
    results, final_query, n_repairs = query_with_repair(g, question)

    if verbose:
        print(f"\nRequête SPARQL générée :\n{final_query}")
        if n_repairs:
            print(f"(après {n_repairs} réparation(s))")

    # Étape 2 : affichage résultats bruts
    raw_output = format_results(results)
    if verbose:
        print(f"\nRésultats bruts :\n{raw_output}")

    # Étape 3 : réponse NL
    answer = generate_answer(question, raw_output)
    print(f"\nRéponse : {answer}")
    return answer

# ---------------------------------------------------------------------------
# Évaluation : baseline vs RAG
# ---------------------------------------------------------------------------

EVAL_QUESTIONS = [
    "Which games were developed by Bohemia Interactive?",
    "What genres does Armello belong to?",
    "What is the best game ?",
    "What is the metacritic score of Assassin's Creed Valhalla?",
    "Which games are similar to Arma 3?",
    "Which studios developed both an Action and RPG game?",
    "What platforms is Always Sometimes Monsters available on?",
    "Which games were published by Devolver Digital?",
]

def evaluate(g: Graph) -> None:
    """
    Compare réponse baseline (LLM seul, sans graphe) vs RAG (LLM + SPARQL).
    Sauvegarde les résultats dans kg_artifacts/rag_evaluation.json
    """
    print("\n" + "=" * 55)
    print("ÉVALUATION : Baseline vs RAG")
    print("=" * 55)

    records = []
    for q in EVAL_QUESTIONS:
        print(f"\nQ: {q}")

        # Baseline : LLM seul
        baseline = call_ollama(
            q,
            system="You are a helpful assistant for video game information. Answer concisely."
        )
        print(f"  Baseline : {baseline[:120]}...")

        # RAG
        results, query, _ = query_with_repair(g, q)
        raw = format_results(results)
        rag_answer = generate_answer(q, raw)
        print(f"  RAG      : {rag_answer[:120]}...")

        records.append({
            "question": q,
            "baseline": baseline,
            "sparql":   query,
            "results":  raw,
            "rag":      rag_answer,
        })

    out = Path(PROJECT_ROOT) / "kg_artifacts" / "rag_evaluation.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"\nÉvaluation sauvegardée → {out}")

# ---------------------------------------------------------------------------
# CLI interactif
# ---------------------------------------------------------------------------

BANNER = """
╔══════════════════════════════════════════════════════╗
║        RAG — Video Game Knowledge Graph              ║
║        Modèle : llama3.2 via Ollama                  ║
╠══════════════════════════════════════════════════════╣
║  Commandes :                                         ║
║    /verbose   — afficher la requête SPARQL générée   ║
║    /eval      — lancer l'évaluation baseline vs RAG  ║
║    /quit      — quitter                              ║
╚══════════════════════════════════════════════════════╝
"""

def cli(g: Graph) -> None:
    print(BANNER)
    verbose = False

    while True:
        try:
            user_input = input("\nQuestion > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAu revoir !")
            break

        if not user_input:
            continue
        if user_input.lower() in ("/quit", "/exit", "quit", "exit"):
            print("Au revoir !")
            break
        if user_input.lower() == "/verbose":
            verbose = not verbose
            print(f"Mode verbose : {'activé' if verbose else 'désactivé'}")
            continue
        if user_input.lower() == "/eval":
            evaluate(g)
            continue

        rag_pipeline(g, user_input, verbose=verbose)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not TTL_FILE.exists():
        print(f"Erreur : fichier introuvable → {TTL_FILE}")
        return

    # Vérifier qu'Ollama tourne
    try:
        requests.get("http://localhost:11434", timeout=3)
    except requests.exceptions.ConnectionError:
        print("Erreur : Ollama n'est pas lancé.")
        print("Lance 'ollama serve' dans un terminal, puis 'ollama pull llama3.2'.")
        return

    g = load_graph(TTL_FILE, INFERRED_FILE)
    cli(g)

if __name__ == "__main__":
    main()