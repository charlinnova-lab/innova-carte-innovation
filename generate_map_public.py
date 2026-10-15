# =========================================================
# CARTOGRAPHIE FILIERE
#   innov'a (c) Charlotte Piau
#   Création : 17 août 2026
#   Last Modification : 
#            25 septembre - Fix Full Mobile Touch & Responsive Sidebar
#            15/10 - FDix nom_court et ligne retour
#   Le fichier :
#   0. interroge le Worker Cloudflare
#   1. stocke les images pour permettre une visualisation tout au long de la journée
#   2. associe chaque catégorie à sa couleur
#   3. récupère les données depuis la base de données Airtable (formulaire de cartographie)
#   4. génère la carte, les filtres, la légende
#   5. prépare l'affichage et l'ancrage GPS
#   6. génère la carte

# =========================================================
# CARTOGRAPHIE FILIERE
#   innov'a (c) Charlotte Piau
#   Création : 17 août 2026
#   Last Modification : Option 2 - Saut de ligne personnalisé
#========================================================= 

import os
import re
import requests
import folium
import markdown
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
    val_str = val_str.replace("Etablissement médical", "Etablissement de santé").replace("Établissement médical", "Etablissement de santé")
    if val_str in COULEURS:
        return COULEURS[val_str]
    for nom_taille, couleur in COULEURS.items():
        if nom_taille.lower() in val_str.lower():
            return couleur
    return COULEURS["Autre"]

def format_url(url):
    if not url:
        return ""
    url_clean = str(url).strip()
    if url_clean in ["#", "", "None", "null"]:
        return ""
    if not (url_clean.startswith("http://") or url_clean.startswith("https://") or url_clean.startswith("mailto:")):
        return f"https://{url_clean}"
    return url_clean

def download_airtable_image(record_id, field_value, prefix="img"):
    if not field_value:
        return ""
    airtable_url, filename = "", ""
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
                val_str = val_str.replace("Etablissement médical", "Etablissement de santé").replace("Établissement médical", "Etablissement de santé")
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
            val_str = str(val).replace("\r\n", "\n").replace("\r", "\n").strip()
            if val_str:
                val_str = _nettoyer_marqueurs_gras_casses(val_str)
                html_rendered = markdown.markdown(val_str, extensions=["nl2br"])
                html_rendered = re.sub(r'<a\s+href=', r'<a target="_blank" rel="noopener noreferrer" href=', html_rendered)
                return html_rendered
    return default

def _nettoyer_marqueurs_gras_casses(text):
    text = re.sub(r'(?<!\S)\*\*(?!\S)', '', text)
    if text.count("**") % 2 != 0:
        text = text.replace("**", "")
    return text

def get_liste_trls_record(record):
    return get_liste_valeurs(record, "TRL_scale", "TRL")

def get_liste_valeurs(record, *keys):
    for key in keys:
        if key in record and record[key] is not None:
            val = record[key]
            items = []
            if isinstance(val, list):
                for v in val:
                    item_str = str(v.get("name", str(v)) if isinstance(v, dict) else str(v)).strip()
                    if item_str:
                        items.append(item_str)
            else:
                val_str = str(val).strip()
                if val_str:
                    items.append(val_str)
            if items:
                return items
    return []

def parse_nom(nom_brut):
    match = re.match(r"^(.*?)\s*\((.*?)\)$", nom_brut)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return nom_brut, nom_brut

def formater_nom_etiquette(actor, nom_court):
    """Gère le retour à la ligne selon la colonne Ligne_retour d'Airtable"""
    ligne_retour_val = get_text(actor, "Ligne_retour", "Saut_ligne")
    if ligne_retour_val:
        if ligne_retour_val.lower() in ["oui", "true", "1", "x"]:
            parts = nom_court.split(" ", 1)
            return f"{parts[0]}<br>{parts[1]}" if len(parts) > 1 else nom_court
        else:
            return ligne_retour_val
    return nom_court

def get_media_url_and_type(record_id, video_field, second_illu):
    if video_field:
        val_str = ""
        if isinstance(video_field, list) and len(video_field) > 0:
            val_str = video_field[0].get("url", "") if isinstance(video_field[0], dict) else str(video_field[0])
        else:
            match = re.search(r"\((https://[^)]+)\)", str(video_field))
            val_str = match.group(1) if match else str(video_field)
        val_str = val_str.strip()
        if val_str:
            youtube_match = re.search(r"(?:v=|/embed/|youtu\.be/|shorts/)([a-zA-Z0-9_-]{11})", val_str)
            if youtube_match:
                return f"https://www.youtube.com/embed/{youtube_match.group(1)}", "youtube"
            vimeo_match = re.search(r"vimeo\.com/(?:video/)?([0-9]+)", val_str)
            if vimeo_match:
                return f"https://player.vimeo.com/video/{vimeo_match.group(1)}", "vimeo"
            if val_str.lower().endswith(('.mp4', '.webm', '.ogg')) or '.mp4?' in val_str.lower():
                return val_str, "video"
    if second_illu:
        local_second_img = download_airtable_image(record_id, second_illu, prefix="second")
        if local_second_img:
            return local_second_img, "image"
    return "", ""

def parse_gps(gps_str):
    if not gps_str:
        return None
    match = re.match(r"([\d.-]+),\s*([\d.-]+)", str(gps_str).strip())
    if match:
        return round(float(match.group(1)), 5), round(float(match.group(2)), 5)
    return None

acteurs = fetch_acteurs()
print(f"✅ {len(acteurs)} acteurs récupérés depuis le Worker")

nb_avant_filtre = len(acteurs)
acteurs = [a for a in acteurs if a.get("Checked") is True]
print(f"✅ {len(acteurs)}/{nb_avant_filtre} fiches conservées (case 'Checked' cochée)")

liste_tailles = list(COULEURS.keys())
liste_tailles_presentes = [t for t in liste_tailles if any(
    get_couleur(get_text(a, "Taille")) == COULEURS[t] for a in acteurs
)]

set_trls = set()
for a in acteurs:
    for t in get_liste_trls_record(a):
        set_trls.add(t)

def tri_trl_key(val):
    match = re.search(r'\d+', val)
    if match:
        return (0, int(match.group()), val)
    return (1, 0, val)

liste_trls = sorted(list(set_trls), key=tri_trl_key)

liste_domaines = sorted(set(
    v for a in acteurs for v in (get_liste_valeurs(a, "Filières", "Filiere", "Domaine") or ["Autre"])
))

CARTO_KEY = "cb1_2w4r_1_3b46deb5d7b181db2c1173a7"
INITIAL_ZOOM = 13
m = folium.Map(
    location=[49.89, 2.30],
    zoom_start=INITIAL_ZOOM,
    tiles=f"https://{{s}}.basemaps.cartocdn.com/rastertiles/light_all/{{z}}/{{x}}/{{y}}{{r}}.png?key={CARTO_KEY}",
    attr="&copy; <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> &copy; <a href='https://carto.com/attributions'>CARTO</a>",
    max_zoom=19,
    subdomains="abcd"
)

html_checkbox_tailles = (
    '<label style="display:flex; align-items:center; gap:8px; font-size:12px; margin-bottom:8px; cursor:pointer; font-weight:bold; border-bottom:1px dashed #CCC; padding-bottom:4px;">'
    '<input type="checkbox" id="master-taille" checked onchange="toggleAllFilters(\'filter-taille\', this)"> Tout cocher / décocher</label>'
) + "".join([
    f'<label style="display:flex; align-items:center; gap:8px; font-size:12px; margin-bottom:5px; cursor:pointer;">'
    f'<input type="checkbox" class="filter-checkbox filter-taille" value="{t}" checked onchange="applyFilters()"> {t}</label>'
    for t in liste_tailles_presentes
])

html_legende_items = "".join([
    f'<div style="display:flex; align-items:center; gap:6px; font-size:11px; color:#333; white-space:nowrap;">'
    f'<div style="width:12px; height:12px; background:{COULEURS[t]}; border-radius:3px; flex-shrink:0; border:1px solid rgba(0,0,0,0.1);"></div>'
    f'<span>{t}</span></div>'
    for t in liste_tailles_presentes
])

html_checkbox_trls = (
    '<label style="display:flex; align-items:center; gap:8px; font-size:12px; margin-bottom:8px; cursor:pointer; font-weight:bold; border-bottom:1px dashed #CCC; padding-bottom:4px;">'
    '<input type="checkbox" id="master-trl" checked onchange="toggleAllFilters(\'filter-trl\', this)"> Tout cocher / décocher</label>'
) + "".join([
    f'<label style="display:flex; align-items:center; gap:8px; font-size:12px; margin-bottom:5px; cursor:pointer;">'
    f'<input type="checkbox" class="filter-checkbox filter-trl" value="{trl}" checked onchange="applyFilters()"> {trl}</label>'
    for trl in liste_trls
])

html_boutons_filiere = (
    '<button onclick="filterFiliere(\'all\', this)" class="filter-btn active" '
    'style="background:#2D3277; color:white; border:none; padding:6px 12px; border-radius:4px; cursor:pointer; font-size:12px; font-weight:bold;">Toutes</button>'
) + "".join([
    f'<button data-value="{d.replace(chr(34), "&quot;")}" onclick="filterFiliere(this.getAttribute(\'data-value\'), this)" class="filter-btn" '
    f'style="background:#EAEAEA; color:#333; border:none; padding:6px 12px; border-radius:4px; cursor:pointer; font-size:12px; font-weight:bold;">{d}</button>'
    for d in liste_domaines
])

ui_and_sidebar_html = """
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">

<style>
.fiche-description p { margin:0 0 6px 0; }
.fiche-description ul, .fiche-description ol { margin:2px 0 8px 0; padding-left:16px; break-inside:avoid-column; }
.fiche-description li { margin-bottom:2px; }
.fiche-description strong { color:#2C3E50; }

.tooltip-text {
    white-space: normal !important;
    word-break: break-word !important;
    overflow-wrap: anywhere !important;
    max-width: min(320px, 80vw) !important;
    width: max-content;
    max-height: 260px;
    overflow-y: auto;
    overflow-x: hidden !important;
}
.tooltip-text p { margin:0 0 6px 0; }
.tooltip-text ul, .tooltip-text ol { margin:2px 0 8px 0; padding-left:18px; }
.tooltip-text li { margin-bottom:3px; }
.tooltip-text a { color:#8FD3FF; text-decoration:underline; }

#sidebar.open {
    right: 0 !important;
}

@media (max-width: 768px) {
    #sidebar {
        width: 100% !important;
        right: -100% !important;
        top: 0 !important;
        height: 100vh !important;
        z-index: 999999 !important;
    }
    .fiche-grid {
        grid-template-columns: 1fr !important;
        min-height: auto !important;
    }
    .fiche-grid > div:first-child {
        height: 180px !important;
        min-height: 180px !important;
    }
    .fiche-description {
        column-count: 1 !important;
        height: auto !important;
        max-height: 220px;
        overflow-y: auto;
    }
    #filiere-bar {
        left: 15px !important;
        top: 10px !important;
        max-width: calc(100vw - 30px) !important;
        overflow-x: auto;
        white-space: nowrap;
    }
    #legend-cartouche {
        left: 15px !important;
        right: 15px !important;
        bottom: 10px !important;
        max-width: calc(100vw - 30px) !important;
    }
    #panel-search, #panel-filter {
        left: 15px !important;
        width: calc(100vw - 30px) !important;
    }
}
</style>

<div id="icon-search-btn" onclick="togglePanel('panel-search', 'icon-search-btn')" title="Recherche" style="
position:fixed; top:calc(50% - 52px); left:15px; width:44px; height:44px; background:white; border-radius:50%;
box-shadow:0 3px 10px rgba(0,0,0,0.25); display:flex; align-items:center; justify-content:center;
font-size:19px; cursor:pointer; z-index:10001;
">🔍</div>

<div id="icon-filter-btn" onclick="togglePanel('panel-filter', 'icon-filter-btn')" title="Filtres" style="
position:fixed; top:calc(50% + 8px); left:15px; width:44px; height:44px; background:white; border-radius:50%;
box-shadow:0 3px 10px rgba(0,0,0,0.25); display:flex; align-items:center; justify-content:center;
font-size:19px; cursor:pointer; z-index:10001;
">🎛️</div>

<div id="filiere-bar" style="
position:fixed; top:15px; left:68px; max-width: calc(100vw - 100px);
background:white; padding:10px 15px; border-radius:8px; z-index:9999;
box-shadow:0 3px 10px rgba(0,0,0,0.2); font-family:Arial,sans-serif;
display:flex; flex-wrap:nowrap; gap:6px; align-items:center; overflow-x:auto;
">
    <span style="font-weight:bold; font-size:13px; color:#2D3277; margin-right:5px; flex-shrink:0;">Filière :</span>
    __HTML_BOUTONS_FILIERE__
</div>

<div id="panel-search" style="
display:none; position:fixed; top:calc(50% - 52px); left:68px; width:260px;
background:white; padding:15px; border-radius:8px; z-index:10000;
box-shadow:0 3px 12px rgba(0,0,0,0.25); font-family:Arial,sans-serif;
">
    <div style="font-weight:bold; font-size:13px; color:#2D3277; margin-bottom:10px; border-bottom:2px solid #2D3277; padding-bottom:5px;">
        🔍 Recherche
    </div>
    <input type="text" id="global-search-input" placeholder="Rechercher un acteur, mot-clé..." onkeyup="applyFilters()" style="
        width:100%; padding:8px 10px; border:1px solid #CCC; border-radius:6px; font-size:12px; box-sizing:border-box; outline:none;
    ">
</div>

<div id="panel-filter" style="
display:none; position:fixed; top:calc(50% + 8px); left:68px; width:280px; max-height: calc(50vh - 30px);
background:white; padding:15px; border-radius:8px; z-index:10000;
box-shadow:0 3px 12px rgba(0,0,0,0.25); font-family:Arial,sans-serif; overflow-y:auto;
">
    <div style="font-weight:bold; font-size:13px; color:#2D3277; margin-bottom:12px; border-bottom:2px solid #2D3277; padding-bottom:5px;">
        🎛️ Filtres interactifs
    </div>

    <div class="accordion-section" style="border-bottom:1px solid #EEE; margin-bottom:6px;">
        <div onclick="toggleAccordion('accordion-tailles')" style="display:flex; justify-content:space-between; align-items:center; cursor:pointer; padding:6px 0;">
            <span style="font-weight:bold; font-size:12px; color:#444;">Type de structure</span>
            <span id="accordion-tailles-arrow" style="font-size:11px; color:#2D3277; transition:transform 0.2s ease;">▾</span>
        </div>
        <div id="accordion-tailles" style="display:none; padding-bottom:10px;">__HTML_CHECKBOX_TAILLES__</div>
    </div>

    <div class="accordion-section" style="margin-bottom:4px;">
        <div onclick="toggleAccordion('accordion-trls')" style="display:flex; justify-content:space-between; align-items:center; cursor:pointer; padding:6px 0;">
            <span style="font-weight:bold; font-size:12px; color:#444;">Échelle TRL</span>
            <span id="accordion-trls-arrow" style="font-size:11px; color:#2D3277; transition:transform 0.2s ease;">▾</span>
        </div>
        <div id="accordion-trls" style="display:
