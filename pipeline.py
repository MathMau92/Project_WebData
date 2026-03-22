"""
Pipeline complet — Web Data Mining & Semantics
Exécute toutes les étapes dans l'ordre :
  1. Crawl des titres        (src/crawl/crawler_titles.py)
  2. Enrichissement RAWG     (src/crawl/crawler_info.py)
  3. Construction du graphe  (src/kg/build_kg.py)
  4. Raisonnement SWRL       (src/reason/reasoning.py)
  5. KGE                     (src/kge/kge.py)
  6. RAG (optionnel)         (src/rag/rag.py)


    python pipeline.py            ← étapes 1 à 5
    python pipeline.py --all      ← étapes 1 à 6 (RAG interactif)
    python pipeline.py --from 3   ← reprendre depuis l'étape 3
    python pipeline.py --only 4   ← une seule étape
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ROOT   = Path(__file__).parent
PYTHON = sys.executable

STEPS = {
    1: ("Crawl — titres Wikipedia",     ROOT / "src/crawl/crawler_titles.py"),
    2: ("Crawl — enrichissement RAWG",  ROOT / "src/crawl/crawler_info.py"),
    3: ("Construction du graphe RDF",   ROOT / "src/kg/build_kg.py"),
    4: ("Raisonnement SWRL",            ROOT / "src/reason/reasoning.py"),
    5: ("KGE (TransE + RotatE)",        ROOT / "src/kge/kge.py"),
    6: ("RAG — pipeline interactif",    ROOT / "src/rag/rag.py"),
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def header(text: str) -> None:
    print(f"\n{'='*58}")
    print(f"  {text}")
    print(f"{'='*58}")


def run_step(step_id: int) -> bool:
    name, script = STEPS[step_id]
    header(f"ÉTAPE {step_id} — {name}")

    if not script.exists():
        print(f"  ⚠ Script introuvable : {script}")
        print(f"  → Étape ignorée.")
        return True  # on continue quand même

    start = time.time()
    result = subprocess.run(
        [PYTHON, str(script)],
        cwd=str(ROOT),
    )
    elapsed = time.time() - start

    if result.returncode == 0:
        print(f"\n  ✓ Étape {step_id} terminée en {elapsed:.1f}s")
        return True
    else:
        print(f"\n  ✗ Étape {step_id} échouée (code {result.returncode})")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Pipeline complet du projet")
    parser.add_argument(
        "--all",    action="store_true",
        help="Inclure l'étape RAG (interactive, désactivée par défaut)"
    )
    parser.add_argument(
        "--from",   dest="from_step", type=int, default=1, metavar="N",
        help="Reprendre depuis l'étape N (défaut: 1)"
    )
    parser.add_argument(
        "--only",   dest="only_step", type=int, default=None, metavar="N",
        help="Exécuter uniquement l'étape N"
    )
    args = parser.parse_args()

    print("""
╔══════════════════════════════════════════════════════════╗
║     Pipeline — Web Data Mining & Semantics               ║
╚══════════════════════════════════════════════════════════╝""")

    # Déterminer les étapes à exécuter
    if args.only_step:
        steps_to_run = [args.only_step]
    else:
        max_step = 6 if args.all else 5
        steps_to_run = list(range(args.from_step, max_step + 1))

    print(f"\n  Étapes : {steps_to_run}")
    total_start = time.time()
    failed = []

    for step_id in steps_to_run:
        if step_id not in STEPS:
            print(f"\n  ⚠ Étape {step_id} inconnue, ignorée.")
            continue

        success = run_step(step_id)
        if not success:
            failed.append(step_id)
            print(f"\n  Arrêt du pipeline à l'étape {step_id}.")
            break

    # Résumé
    total = time.time() - total_start
    print(f"\n{'='*58}")
    if not failed:
        print(f"   Pipeline terminé en {total:.1f}s")
    else:
        print(f"   Pipeline interrompu — étapes échouées : {failed}")
    print(f"{'='*58}\n")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()