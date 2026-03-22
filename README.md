# Video Game Knowledge Graph

A full Knowledge Engineering pipeline over video games — from web crawling to RAG-powered question answering.

**Domain**: RPG and action-RPG video games  
**Data sources**: Wikipedia FR + RAWG API  
**Stack**: Python 3.13, rdflib, owlready2, PyKEEN, Ollama (llama3.2)

---

## Project Structure

```
Project_WebData/
├── pipeline.py                  ← run everything
├── requirements.txt
├── data/
│   ├── titles.json              ← Wikipedia titles (step 1)
│   ├── family.owl               ← family ontology (step 4A)
│   ├── raw/
│   │   └── all_games.json       ← enriched game data (step 2)
│   └── kge/
│       ├── train.txt            ← KGE splits (step 5)
│       ├── valid.txt
│       └── test.txt
├── kg_artifacts/
│   ├── ontology.ttl             ← RDF knowledge base (step 3)
│   ├── swrl_inferred.ttl        ← SWRL inferred triples (step 4)
│   ├── kge_results.csv          ← TransE / RotatE metrics (step 5)
│   ├── kge_sensitivity.csv      ← size-sensitivity analysis (step 5)
│   ├── kge_tsne_transe.png      ← t-SNE TransE (step 5)
│   ├── kge_tsne_rotate.png      ← t-SNE RotatE (step 5)
│   └── rag_evaluation.json      ← baseline vs RAG results (step 6)
└── src/
    ├── crawl/
    │   ├── crawler_titles.py    ← step 1: Wikipedia titles
    │   └── crawler_info.py      ← step 2: RAWG enrichment
    ├── kg/
    │   └── build_kg.py          ← step 3: RDF graph
    ├── reason/
    │   └── reasoning.py         ← step 4: SWRL (owlready2 + Pellet)
    ├── kge/
    │   └── kge.py               ← step 5: TransE + RotatE (PyKEEN)
    └── rag/
        └── rag.py               ← step 6: RAG CLI (Ollama)
```

---

## Quickstart

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

> **Java 17+** is required for the SWRL reasoner (Pellet).  
> Download at: https://adoptium.net

> **Ollama** is required for the RAG pipeline.  
> Download at: https://ollama.com, then:
> ```bash
> ollama pull llama3.2
> ```

### 2. Run the full pipeline

```bash
# Steps 1 to 5 (crawl → graph → reasoning → KGE)
python pipeline.py

# Include the interactive RAG demo (step 6)
python pipeline.py --all

# Resume from a specific step (e.g. if crawl is already done)
python pipeline.py --from 3

# Run a single step
python pipeline.py --only 4
```

### 3. Run the RAG demo interactively

```bash
# Make sure Ollama is running first
ollama serve   # (or it may already be running in background)

python src/rag/rag.py
```

**CLI commands inside the RAG demo:**

| Command    | Description                              |
|------------|------------------------------------------|
| `/verbose` | Show the generated SPARQL query          |
| `/eval`    | Run baseline vs RAG evaluation (8 questions) |
| `/quit`    | Exit                                     |

**Example questions:**
```
> Which games were developed by Bohemia Interactive?
> What genres does Armello belong to?
> Which games have a metacritic score above 80?
> What platforms is Always Sometimes Monsters available on?
> Which games are similar to Arma 3?
```

---

## Pipeline Steps

| Step | Script | Description | Output |
|------|--------|-------------|--------|
| 1 | `crawler_titles.py` | Collect titles from Wikipedia FR | `data/titles.json` |
| 2 | `crawler_info.py` | Enrich with RAWG API | `data/raw/all_games.json` |
| 3 | `build_kg.py` | Build RDF ontology + SPARQL expansion | `kg_artifacts/ontology.ttl` |
| 4 | `reasoning.py` | SWRL rules with owlready2 + Pellet | `kg_artifacts/swrl_inferred.ttl` |
| 5 | `kge.py` | Train TransE + RotatE, evaluate MRR/Hits@k | `kg_artifacts/kge_results.csv` |
| 6 | `rag.py` | NL→SPARQL RAG with self-repair loop | `kg_artifacts/rag_evaluation.json` |

---

## Key Results

### Knowledge Base (233 games)

| Metric | Value |
|--------|-------|
| Total triples | 11,330 |
| Games | 224 |
| Studios | 250 |
| Publishers | 160 |
| Platforms | 40 |
| Genres | 17 |

### KGE (100 epochs, 622 triples)

| Model | MRR | Hits@1 | Hits@3 | Hits@10 |
|-------|-----|--------|--------|---------|
| TransE | 0.243 | 0.056 | 0.315 | 0.611 |
| **RotatE** | **0.530** | **0.389** | **0.630** | **0.796** |

RotatE outperforms TransE because the graph contains many symmetric relations (`similarTo`, `sameStudioAs`) that RotatE handles natively via complex rotations.

### RAG Evaluation

RAG wins 6/8 questions over the baseline (llama3.2 alone), mainly by eliminating hallucinated facts and grounding answers in the actual knowledge base.

---

## Notes

- The `owl:equivalentProperty` alignments to schema.org in `ontology.ttl` are stripped before loading into OWL reasoners to avoid inconsistency errors.
- RotatE embeddings are complex-valued — the module `|z|` is taken before t-SNE and cosine similarity computation.
- The RAG pipeline loads both `ontology.ttl` and `swrl_inferred.ttl` at startup, making inferred relations (isAAA, isSelfPublished) queryable.

---

## Requirements

```
Python 3.13+
Java 17+ (for Pellet reasoner)
Ollama (for RAG)
```

See `requirements.txt` for Python dependencies.

---

## Author

Mathieu Maury & Isabela Mora— ESILV A4  
Web Data Mining & Semantics — 2025–2026