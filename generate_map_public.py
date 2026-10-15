# =========================================================
# CARTOGRAPHIE FILIERE
#   innov'a (c) Charlotte Piau
#   Création : 17 août 2026
#   Last Modification : 25 septembre - Fix Full Mobile Touch & Responsive Sidebar
#  15/10 : nom court, nom_long

#   Le fichier :
#   0. interroge le Worker Cloudflare
#   1. stocke les images pour permettre une visualisation tout au long de la journée
#   2. associe chaque catégorie à sa couleur
#   3. récupère les données depuis la base de données Airtable (formulaire de cartographie)
#   4. génère la carte, les filtres, la légende
#   5. prépare l'affichage et l'ancrage GPS
#   6. génère la carte

#   IMPORTANT : Le token Airtable n'est PAS présent ici. Il est stocké comme secret dans Cloudflare.
#========================================================= 

import os
import re
import requests
import folium
import markdown  # pip install markdown --break-system-packages
from urllib.parse import quote
from collections import defaultdict

# ==================================
# 0. CONFIGURATION
# ==================================
WORKER_URL = "https://flat-forest-26c8.charlottepiau-innova.workers.dev/"
TABLE = "Cartographie"
MODE = "public"
CONTACT_PUBLIC_EMAIL = "contact@innov-a.com"
CONTACT_PUBLIC_SUJET = "Demande de mise en relation"

# Dossier d'accueil des images
os.makedirs("assets/images", exist_ok=True)

COULEURS = {
    "Etablissement de santé":                       "#2D3277", #bleu marine
    "Etablissement de formation":                    "#845EC2", #violet
    "Laboratoire ou activité de recherche":          "#FBC9D4", #rose pâle
    "Plateforme technologique ou centre technique": "#FB6F92", #rose
    "Structure d'accompagnement à l'innovation":    "#FDC500", #jaune
    "Start-up":                                      "#9BC045", #vert
    "TPE ou PME":                                    "#00EBF5", #bleu ciel
    "Grande entreprise":                            "#2583F2", #bleu moyen
    "Association":                                  "#FFC27F", #orange pâle
    "Projet collaboratif":                          "#E8873A", #orange
    "Autre":                                        "#888888", #gris
}

def get_couleur(taille_valeur):
    if not taille_valeur:
        return COULEURS["Autre"]
    val_str = str(taille_valeur).strip().replace("\n", " ").replace("\r", "")
    val_str = val_str.replace("Etablissement médical", "Etablissement de santé").replace("Établissement médical", "Établissement de santé")
    if val_str in COULEURS:
        return COULEURS[val_str]
    for nom_taille, couleur in COULEURS.items():
        if nom_taille.lower() in val_str.lower():
            return couleur
    return COULEURS["Autre"]

def format_url(url):
    """S'assure que l'URL commence par http:// ou https:// pour éviter les erreurs de redirection locale."""
    if not url:
        return ""
    url_clean = str(url).strip()
    if url_clean in ["#", "", "None", "null"]:
        return ""
    if not (url_clean.startswith("http://") or url_clean.startswith("https://") or url_clean.startswith("mailto:")):
        return f"https://{url_clean}"
    return url_clean

# ==================================
# 1. HELPER POUR TÉLÉCHARGEMENT LOCAL DES IMAGES
# ==================================
def download_airtable_image(record_id, field_value, prefix="img"):
    if not field_value:
        return ""
    
    airtable_url = ""
    filename = ""
    
    if isinstance(field_value, list) and len(field_value) > 0:
        if isinstance(field_value[0], dict):
            airtable_url = field_value[0].get("url", "")
            filename = field_value[0].get("filename", "")
        else:
            airtable_url = str(field_value[0])
    elif str(field_value).startswith("http"):
        airtable_url = str(field_value)
    else:
        match = re.search(r"\((https://[^)]+)\)", str(field_value))
        if match:
            airtable_url = match.group(1)

    if not airtable_url:
        return ""

    ext = filename.split(".")[-1] if "." in filename else "png"
    ext = ext.split("?")[0].lower()
    if ext not in ["jpg", "jpeg", "png", "gif", "webp", "svg"]:
        ext = "png"

    local_path = f"assets/images/{record_id}_{prefix}.{ext}"

    try:
        res = requests.get(airtable_url, timeout=10)
        if res.status_code == 200:
            with open(local_path, "wb") as f:
                f.write(res.content)
            return local_path
    except Exception as e:
        print(f"⚠️ Erreur téléch. {prefix} ({record_id}) : {e}")

    return ""

# ==================================
# 2. RECUPERATION ET PARSING WORKER
# ==================================
def fetch_acteurs():
    records, offset = [], None
    while True:
        params = {"pageSize": 100}
        if offset:
            params["offset"] = offset
        
        res = requests.get(WORKER_URL, params=params)
        res.raise_for_status()
        
        data = res.json()
        
        for r in data.get("records", []):
            rec_fields = r.get("fields", {})
            rec_fields["_record_id"] = r.get("id")
            records.append(rec_fields)
        
        offset = data.get("offset")
        if not offset:
            break
            
    return records

def get_text(record, *keys, default=""):
    for key in keys:
        if key in record and record[key] is not None:
            val = record[key]
            if isinstance(val, list):
                extracted = [str(v.get("name", str(v))) if isinstance(v, dict) else str(v) for v in val]
                val = ", ".join(extracted)
            elif isinstance(val, dict):
                val = val.get("name", str(val))
            
            val_str = str(val).strip().replace("\r\n", "\n").replace("\r", "\n")
            if val_str:
                val_str = val_str.replace("Etablissement médical", "Etablissement de santé").replace("Établissement médical", "Établissement de santé")
                return val_str
    return default

def get_rich_text_html(record, *keys, default=""):
    for key in keys:
        if key in record and record[key] is not None:
            val = record[key]
            if isinstance(val, list):
                extracted = [str(v.get("name", str(v))) if isinstance(v, dict) else str(v) for v in val]
                val = "\n".join(extracted)
            elif isinstance(val, dict):
                val = val.get("name", str(val))
