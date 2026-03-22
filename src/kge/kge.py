import os
import random
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from rdflib import Graph, URIRef
from sklearn.manifold import TSNE

# ---------------------------------------------------------------------------
# Chemins
# ---------------------------------------------------------------------------

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
# kge/ est directement sous la racine du projet
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

TTL_FILE  = Path(PROJECT_ROOT) / "kg_artifacts" / "ontology.ttl"
KGE_DIR   = Path(PROJECT_ROOT) / "data" / "kge"
OUT_DIR   = Path(PROJECT_ROOT) / "kg_artifacts"

# Propriétés à garder pour le KGE (les relations les plus riches sémantiquement)
KEEP_PREDICATES = {
    "http://videogamekg.org/ontology#developedBy",
    "http://videogamekg.org/ontology#publishedBy",
    "http://videogamekg.org/ontology#hasGenre",
    "http://videogamekg.org/ontology#availableOn",
    "http://videogamekg.org/ontology#sameStudioAs",
    "http://videogamekg.org/ontology#similarTo",
}

SEED = 42

# ---------------------------------------------------------------------------
# Étape 1 — Extraire les triplets depuis ontology.ttl
# ---------------------------------------------------------------------------

def extract_triples(ttl_path: Path) -> list[tuple[str, str, str]]:
    """
    Charge le graphe RDF et extrait les triplets (sujet, prédicat, objet)
    en ne gardant que les relations sémantiques utiles pour le KGE.
    Les littéraux (dates, scores...) sont exclus : KGE travaille sur des entités.
    """
    print(f"Chargement de {ttl_path}...")
    g = Graph()
    with open(ttl_path, "rb") as f:
        g.parse(f, format="turtle")
    print(f"  {len(g)} triplets chargés")

    triples = []
    for s, p, o in g:
        # Garder uniquement object properties (pas les littéraux)
        if not isinstance(o, URIRef):
            continue
        if str(p) not in KEEP_PREDICATES:
            continue
        # Raccourcir les URIs pour lisibilité
        s_short = str(s).split("/")[-1].split("#")[-1]
        p_short = str(p).split("#")[-1]
        o_short = str(o).split("/")[-1].split("#")[-1]
        triples.append((s_short, p_short, o_short))

    print(f"  {len(triples)} triplets utiles extraits")
    return triples


# ---------------------------------------------------------------------------
# Étape 2 — Créer les splits train / valid / test
# ---------------------------------------------------------------------------

def create_splits(
    triples: list[tuple],
    train_ratio: float = 0.8,
    valid_ratio: float = 0.1,
) -> tuple[list, list, list]:
    """Split 80 / 10 / 10 avec mélange aléatoire."""
    random.seed(SEED)
    shuffled = triples.copy()
    random.shuffle(shuffled)

    n = len(shuffled)
    n_train = int(n * train_ratio)
    n_valid = int(n * valid_ratio)

    train = shuffled[:n_train]
    valid = shuffled[n_train:n_train + n_valid]
    test  = shuffled[n_train + n_valid:]

    print(f"\nSplits :")
    print(f"  train : {len(train)} triplets ({len(train)/n:.0%})")
    print(f"  valid : {len(valid)} triplets ({len(valid)/n:.0%})")
    print(f"  test  : {len(test)} triplets ({len(test)/n:.0%})")
    return train, valid, test


def save_splits(train, valid, test, out_dir: Path) -> None:
    """Sauvegarde au format TSV attendu par PyKEEN."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, data in [("train", train), ("valid", valid), ("test", test)]:
        path = out_dir / f"{name}.txt"
        with open(path, "w", encoding="utf-8") as f:
            for s, p, o in data:
                f.write(f"{s}\t{p}\t{o}\n")
        print(f"  Sauvegardé : {path}")


# ---------------------------------------------------------------------------
# Étape 3 — Entraîner les modèles KGE avec PyKEEN
# ---------------------------------------------------------------------------

def train_model(model_name: str, kge_dir: Path, epochs: int = 100) -> dict:
    """
    Entraîne un modèle KGE et retourne les métriques MRR / Hits@k.
    PyKEEN gère automatiquement l'évaluation sur le set de test.
    """
    from pykeen.pipeline import pipeline
    from pykeen.triples import TriplesFactory

    print(f"\n{'='*50}")
    print(f"Entraînement : {model_name} ({epochs} epochs)")
    print(f"{'='*50}")

    result = pipeline(
        training=str(kge_dir / "train.txt"),
        validation=str(kge_dir / "valid.txt"),
        testing=str(kge_dir / "test.txt"),
        model=model_name,
        training_kwargs=dict(num_epochs=epochs, batch_size=64),
        random_seed=SEED,
        # Évaluation automatique MRR + Hits@1/3/10
        evaluation_kwargs=dict(use_tqdm=False),
    )

    # Extraire les métriques clés
    metrics = result.metric_results
    mrr     = metrics.get_metric("mean_reciprocal_rank")
    hits1   = metrics.get_metric("hits_at_1")
    hits3   = metrics.get_metric("hits_at_3")
    hits10  = metrics.get_metric("hits_at_10")

    print(f"\nRésultats {model_name} :")
    print(f"  MRR      : {mrr:.4f}")
    print(f"  Hits@1   : {hits1:.4f}")
    print(f"  Hits@3   : {hits3:.4f}")
    print(f"  Hits@10  : {hits10:.4f}")

    return {
        "model":    model_name,
        "epochs":   epochs,
        "MRR":      round(mrr,   4),
        "Hits@1":   round(hits1, 4),
        "Hits@3":   round(hits3, 4),
        "Hits@10":  round(hits10, 4),
        "result":   result,   # objet complet pour t-SNE
    }


# ---------------------------------------------------------------------------
# Étape 4 — Analyse de sensibilité à la taille
# ---------------------------------------------------------------------------

def sensitivity_analysis(
    triples: list[tuple],
    kge_dir: Path,
    model_name: str = "TransE",
    sizes: list[int] = None,
) -> pd.DataFrame:
    """
    Entraîne le même modèle sur des sous-ensembles de tailles différentes
    pour mesurer l'impact du volume de données sur les métriques.
    """
    if sizes is None:
        n = len(triples)
        # Prend 3 tailles : ~33%, ~66%, 100%
        sizes = [max(30, n // 3), max(60, 2 * n // 3), n]

    records = []
    for size in sizes:
        print(f"\n--- Sensibilité : {size} triplets ---")
        subset = triples[:size]
        train, valid, test = create_splits(subset)

        # Évite les splits trop petits
        if len(test) < 5:
            print("  Set de test trop petit, ignoré.")
            continue

        # Sauvegarde temporaire
        tmp_dir = kge_dir / f"tmp_{size}"
        save_splits(train, valid, test, tmp_dir)

        result = train_model(model_name, tmp_dir, epochs=50)
        result["n_triples"] = size
        records.append({k: v for k, v in result.items() if k != "result"})

        # Nettoyage
        import shutil
        shutil.rmtree(tmp_dir)

    df = pd.DataFrame(records)
    print("\n── Sensibilité à la taille ──────────────────")
    print(df.to_string(index=False))
    return df


# ---------------------------------------------------------------------------
# Étape 5 — Visualisation t-SNE
# ---------------------------------------------------------------------------

def plot_tsne(result, out_path: Path, model_name: str) -> None:
    """
    Réduit les embeddings d'entités à 2D avec t-SNE et
    colorie par type d'entité (Game, Studio, Genre...).
    """
    try:
        entity_embeddings = (
            result.model.entity_representations[0]
            (indices=None)
            .detach()
            .cpu()
            .numpy()
        )
    except Exception as e:
        print(f"  t-SNE impossible : {e}")
        return

    # RotatE produit des embeddings complexes → prendre le module
    if np.iscomplexobj(entity_embeddings):
        entity_embeddings = np.abs(entity_embeddings)

    # Réduire à 2D
    print(f"\nCalcul t-SNE sur {entity_embeddings.shape[0]} entités...")
    n_components = min(2, entity_embeddings.shape[0] - 1)
    tsne = TSNE(n_components=2, random_state=SEED, perplexity=min(30, entity_embeddings.shape[0] // 4))
    coords = tsne.fit_transform(entity_embeddings)

    # Récupérer les labels
    entity_to_id = result.training.entity_to_id
    id_to_entity = {v: k for k, v in entity_to_id.items()}

    # Colorier par type selon le nom de l'entité
    def get_color(name: str) -> str:
        n = name.lower()
        if any(g in n for g in ["rpg", "action", "adventure", "strategy", "puzzle", "indie", "shooter", "casual", "simulation"]):
            return "#1D9E75"   # vert → genres
        elif any(s in n for s in ["studio", "interactive", "games", "entertainment", "soft", "digital"]):
            return "#7F77DD"   # violet → studios
        else:
            return "#378ADD"   # bleu → jeux

    colors = [get_color(id_to_entity.get(i, "")) for i in range(len(coords))]

    fig, ax = plt.subplots(figsize=(12, 8))
    ax.scatter(coords[:, 0], coords[:, 1], c=colors, alpha=0.6, s=30)

    # Annoter quelques entités connues
    known = {"Armello", "Arma_3", "RPG", "Action", "Bohemia_Interactive",
             "League_of_Geeks", "Assassin_s_Creed_Valhalla", "Indie"}
    for i, (x, y) in enumerate(coords):
        name = id_to_entity.get(i, "")
        if name in known:
            ax.annotate(name, (x, y), fontsize=7, alpha=0.9,
                        xytext=(4, 4), textcoords="offset points")

    # Légende manuelle
    from matplotlib.patches import Patch
    legend = [
        Patch(color="#1D9E75", label="Genres"),
        Patch(color="#7F77DD", label="Studios"),
        Patch(color="#378ADD", label="Jeux"),
    ]
    ax.legend(handles=legend, loc="upper right")
    ax.set_title(f"t-SNE des embeddings — {model_name}", fontsize=13)
    ax.set_xlabel("Dim 1")
    ax.set_ylabel("Dim 2")
    ax.grid(True, alpha=0.2)

    plt.tight_layout()
    plt.savefig(str(out_path), dpi=150)
    plt.close()
    print(f"  t-SNE sauvegardé → {out_path}")


# ---------------------------------------------------------------------------
# Étape 6 — Voisins les plus proches
# ---------------------------------------------------------------------------

def nearest_neighbors(result, entity_name: str, k: int = 5) -> None:
    """
    Affiche les k entités les plus proches d'une entité donnée
    dans l'espace des embeddings (distance cosinus).
    """
    from torch.nn.functional import cosine_similarity
    import torch

    entity_to_id = result.training.entity_to_id
    id_to_entity = {v: k for k, v in entity_to_id.items()}

    if entity_name not in entity_to_id:
        print(f"  Entité '{entity_name}' introuvable dans le graphe.")
        return

    embeddings = (
        result.model.entity_representations[0](indices=None)
        .detach()
    )
    # RotatE produit des embeddings complexes → prendre le module
    if embeddings.is_complex():
        embeddings = embeddings.abs()
    idx    = entity_to_id[entity_name]
    target = embeddings[idx].unsqueeze(0)
    sims   = cosine_similarity(target, embeddings).squeeze()
    top_k  = sims.topk(k + 1).indices.tolist()

    print(f"\n  Voisins les plus proches de '{entity_name}' :")
    for i in top_k:
        if i != idx:
            print(f"    {id_to_entity[i]:40s}  sim={sims[i].item():.4f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    KGE_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Extraction des triplets
    print("=" * 50)
    print("ÉTAPE 4A — Préparation des données")
    print("=" * 50)
    triples = extract_triples(TTL_FILE)

    if len(triples) < 30:
        print(f"\nAttention : seulement {len(triples)} triplets extraits.")
        print("Vérifie que ontology.ttl contient bien les propriétés listées dans KEEP_PREDICATES.")
        return

    # 2. Splits
    train, valid, test = create_splits(triples)
    save_splits(train, valid, test, KGE_DIR)

    # 3. Entraînement des modèles
    print("\n" + "=" * 50)
    print("ÉTAPE 4B — Entraînement KGE")
    print("=" * 50)

    all_results = []
    for model_name in ["TransE", "RotatE"]:
        r = train_model(model_name, KGE_DIR, epochs=100)
        all_results.append(r)

        # t-SNE
        tsne_path = OUT_DIR / f"kge_tsne_{model_name.lower()}.png"
        plot_tsne(r["result"], tsne_path, model_name)

        # Voisins les plus proches
        nearest_neighbors(r["result"], "Armello")
        nearest_neighbors(r["result"], "RPG")

    # 4. Tableau comparatif
    print("\n" + "=" * 50)
    print("ÉTAPE 4C — Comparaison des modèles")
    print("=" * 50)
    df = pd.DataFrame([{k: v for k, v in r.items() if k != "result"} for r in all_results])
    print(df.to_string(index=False))

    csv_path = OUT_DIR / "kge_results.csv"
    df.to_csv(str(csv_path), index=False)
    print(f"\nRésultats sauvegardés → {csv_path}")

    # 5. Analyse de sensibilité
    print("\n" + "=" * 50)
    print("ÉTAPE 4D — Sensibilité à la taille")
    print("=" * 50)
    df_sensitivity = sensitivity_analysis(triples, KGE_DIR, model_name="TransE")
    sens_path = OUT_DIR / "kge_sensitivity.csv"
    df_sensitivity.to_csv(str(sens_path), index=False)
    print(f"Sensibilité sauvegardée → {sens_path}")

    print("\n=== KGE terminé ===")


if __name__ == "__main__":
    main()