import requests
from bs4 import BeautifulSoup
import csv
import time
import os
import re

BASE_URL = "https://fr.wikipedia.org"
LIST_URL = "https://fr.wikipedia.org/wiki/Oscar_du_meilleur_film"
HEADERS = {"User-Agent": "ProjetEtudiantWebDatamining (mathieu.maury@edu.devinci.fr)"}

def get_oscar_winners():
    print(f"Extraction des films oscarisés depuis {LIST_URL}...")
    try:
        response = requests.get(LIST_URL, headers=HEADERS)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        links = []
        # On cherche tous les liens <a> sur la page
        all_a = soup.find_all('a', href=True)
        print(f"DEBUG: Nombre total de liens trouvés sur la page: {len(all_a)}")

        for a in all_a:
            href = a['href']
            text = a.get_text().strip()
            
            # FILTRE STRICT :
            # 1. Lien interne Wikipédia
            # 2. Le texte du lien n'est pas vide
            # 3. On évite les années (ex: 1927 au cinéma) et les catégories
            if href.startswith('/wiki/') and len(text) > 1:
                if not any(x in href.lower() for x in [':', 'oscar', 'cinéma', 'portail', 'index']):
                    # Pour l'Oscar du meilleur film, les titres sont souvent en italique <i>
                    # ou alors ce sont les liens principaux des tableaux
                    links.append(BASE_URL + href)
        
        # On garde les liens qui apparaissent fréquemment ou qui semblent être des films
        # (Les films oscarisés apparaissent souvent dans les tableaux de synthèse en bas de page aussi)
        unique_links = sorted(list(set(links)))
        
        # Petit hack : si on en trouve trop, on filtre pour ne garder que ceux 
        # qui ont un titre de film probable (commence par une majuscule)
        final_links = [l for l in unique_links if l.split('/')[-1][0].isupper()]
        
        return final_links
    except Exception as e:
        print(f"Erreur lors de la requête : {e}")
        return []
def scrape_film_details(url):
    print(f"Scraping : {url}")
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        data = {"url": url, "titre": "", "réalisateur": "", "genre": "", "année": ""}
        
        # Titre
        title = soup.find('h1', id='firstHeading')
        if title: data["titre"] = title.text

        # Infobox
        infobox = soup.find('table', class_='infobox')
        if infobox:
            for row in infobox.find_all('tr'):
                header = row.find('th')
                value = row.find('td')
                if header and value:
                    txt = header.text.strip().lower()
                    if "réalisation" in txt:
                        data["réalisateur"] = value.get_text(separator=", ").strip()
                    elif "genre" in txt:
                        data["genre"] = value.get_text(separator=", ").strip()
                    elif "sortie" in txt:
                        year = re.search(r'\d{4}', value.text)
                        if year: data["année"] = year.group()
        return data
    except Exception as e:
        print(f"Erreur sur {url}: {e}")
        return None

def main():
    film_links = get_oscar_winners()
    print(f"Nombre de films trouvés : {len(film_links)}")
    
    if len(film_links) == 0:
        print("Erreur : Aucun lien trouvé. Vérifiez la structure de la page.")
        return

    all_films = []
    # On en prend 40 pour avoir un bon échantillon sans attendre trop longtemps
    for link in film_links[:40]:
        info = scrape_film_details(link)
        if info:
            all_films.append(info)
        time.sleep(0.5) # Un peu plus rapide mais toujours respectueux

    os.makedirs('data', exist_ok=True)
    with open('data/oscar_films.csv', 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["url", "titre", "réalisateur", "genre", "année"])
        writer.writeheader()
        writer.writerows(all_films)
    print(f"\nTerminé ! {len(all_films)} films sauvegardés dans data/oscar_films.csv")

if __name__ == "__main__":
    main()