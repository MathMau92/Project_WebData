import rdflib
from rdflib import Namespace, RDF, OWL
import os

def run_simple_reasoning(input_ttl):
    print("Chargement du graphe...")
    g = rdflib.Graph()
    g.parse(input_ttl, format="turtle")
    
    # Définition de ton namespace
    VG = Namespace("http://videogamekg.org/ontology#")
    g.bind("vg", VG)

    print("Exécution du raisonnement logique (Inférence)...")
    
    # On va simuler la règle SWRL : 
    # Si (Jeu1 -> developedBy -> Studio) ET (Jeu2 -> developedBy -> Studio)
    # ALORS (Jeu1 -> sameStudioAs -> Jeu2)
    
    new_triplets = []
    
    # On cherche tous les jeux et leurs développeurs
    # triplet1 : (jeu1, developedBy, studio)
    for s1, p1, o1 in g.triples((None, VG.developedBy, None)):
        # Pour chaque studio trouvé, on cherche les AUTRES jeux du même studio
        # triplet2 : (jeu2, developedBy, même_studio)
        for s2, p2, o2 in g.triples((None, VG.developedBy, o1)):
            if s1 != s2: # On évite de dire qu'un jeu est le même studio que lui-même
                new_triplets.append((s1, VG.sameStudioAs, s2))

    # Ajouter les nouveaux triplets au graphe
    count = 0
    for triple in new_triplets:
        if triple not in g:
            g.add(triple)
            count += 1

    print(f"Raisonnement terminé : {count} nouvelles relations 'sameStudioAs' créées.")

    # Sauvegarde du graphe enrichi
    output_path = "./kg_artifacts/knowledge_graph_enriched.ttl"
    g.serialize(destination=output_path, format="turtle")
    print(f"Fichier sauvegardé : {output_path}")

if __name__ == "__main__":
    # Gestion des chemins
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    input_file = os.path.join(project_root, "kg_artifacts", "ontology.ttl")
    
    if os.path.exists(input_file):
        run_simple_reasoning(input_file)
    else:
        print(f"Erreur : Le fichier {input_file} est introuvable.")