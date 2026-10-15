# =========================================================
# CARTOGRAPHIE FILIERE
#   innov'a (c) Charlotte Piau
#   Création : 17 août 2026
#   Last Modification : 
#            25 septembre - Fix Full Mobile Touch & Responsive Sidebar
#            15/10 - Ajout boutons zoom +/-, fix TRL et Name_group hubs
#   Le fichier :
#   0. interroge le Worker Cloudflare
#   1. stocke les images pour permettre une visualisation tout au long de la journée
#   2. associe chaque catégorie à sa couleur
#   3. récupère les données depuis la base de données Airtable (formulaire de cartographie)
#   4. génère la carte, les filtres, la légende
#   5. prépare l'affichage et l'ancrage GPS
#   6. génère la carte
# =========================================================

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
    "Etablissement de santé":                       "#2D3277",
    "Etablissement de formation":                    "#845EC2",
    "Laboratoire ou activité de recherche":          "#FBC9D4",
    "Plateforme technologique ou centre technique": "#FB6F92",
    "Structure d'accompagnement à l'innovation":    "#FDC500",
    "Start-up":                                      "#9BC045",
    "TPE ou PME":                                    "#00EBF5",
    "Grande entreprise":                            "#2583F2",
    "Association":                                  "#FFC27F",
    "Projet collaboratif":                          "#E8873A",
    "Autre":                                        "#888888",
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
    """Récupère et découpe proprement les TRL même si Airtable les renvoie groupés en bloc"""
    brut = get_liste_valeurs(record, "TRL_scale", "TRL")
    trls_nettoyes = []
    
    for item in brut:
        if "TRL" in item and item.count("TRL") > 1:
            morceaux = re.split(r'(?=\bTRL\s+\d+)', item)
            for m in morceaux:
                m_clean = m.strip()
                if m_clean:
                    trls_nettoyes.append(m_clean)
        else:
            item_clean = item.strip()
            if item_clean:
                trls_nettoyes.append(item_clean)
                
    return trls_nettoyes

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
    """Gère l'icône et Name_group pour les ensembles de projets, et la règle de ligne_retour pour les fiches uniques"""
    type_fiche = get_text(actor, "type_fiche", "Type_fiche", "Type").strip().lower()
    
    # 1. Si c'est un ensemble de projets (Hub), on utilise Name_group (ou nom_court) avec l'icône
    if type_fiche == "ensemble de projets":
        nom_groupe_field = ""
        for k in ["Name_group", "name_group", "Name group", "Nom_groupe", "nom_groupe"]:
            if k in actor and actor[k] is not None:
                val = str(actor[k]).strip().replace("\r\n", "\n").replace("\r", "\n")
                if val:
                    nom_groupe_field = val
                    break
        
        nom_a_utiliser = nom_groupe_field if nom_groupe_field else nom_court
        nom_a_utiliser_html = nom_a_utiliser.replace("\n", "<br>")
        return f"🏢 {nom_a_utiliser_html}"

    # 2. Pour les autres fiches (uniques, etc.), on vérifie la case Ligne_retour
    ligne_retour_val = None
    for k, v in actor.items():
        if k.lower() in ["ligne_retour", "saut_ligne", "retour_ligne"]:
            ligne_retour_val = v
            break

    est_coche = False
    if isinstance(ligne_retour_val, bool) and ligne_retour_val is True:
        est_coche = True
    elif isinstance(ligne_retour_val, list):
        est_coche = any(v is True or str(v).lower() in ["true", "1", "oui", "yes", "x"] for v in ligne_retour_val)
    elif ligne_retour_val is not None:
        val_str = str(ligne_retour_val).strip().lower()
        if val_str in ["true", "1", "oui", "yes", "x", "on"]:
            est_coche = True

    if est_coche:
        if "\n" in nom_court:
            return nom_court.replace("\n", "<br>")
        if " " in nom_court:
            parts = nom_court.split(" ", 1)
            return f"{parts[0]}<br>{parts[1]}"
        elif "-" in nom_court:
            parts = nom_court.split("-", 1)
            return f"{parts[0]}-<br>{parts[1]}"
    
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

# Chargement propre des fichiers externes CSS et JS
css_content = ""
if os.path.exists("assets/css/style.css"):
    with open("assets/css/style.css", "r", encoding="utf-8") as f:
        css_content = f.read()

js_content = ""
if os.path.exists("assets/js/map_logic.js"):
    with open("assets/js/map_logic.js", "r", encoding="utf-8") as f:
        js_content = f.read()

ui_and_sidebar_html = f"""
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">

<!-- Google Analytics -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', 'G-XXXXXXXXXX');
</script>

<style>
{css_content}
</style>

<div id="icon-search-btn" onclick="togglePanel('panel-search', 'icon-search-btn')" title="Recherche" style="
position:fixed; top:calc(50% - 82px); left:15px; width:44px; height:44px; background:white; border-radius:50%;
box-shadow:0 3px 10px rgba(0,0,0,0.25); display:flex; align-items:center; justify-content:center;
font-size:19px; cursor:pointer; z-index:10001;
">🔍</div>

<div id="icon-filter-btn" onclick="togglePanel('panel-filter', 'icon-filter-btn')" title="Filtres" style="
position:fixed; top:calc(50% - 22px); left:15px; width:44px; height:44px; background:white; border-radius:50%;
box-shadow:0 3px 10px rgba(0,0,0,0.25); display:flex; align-items:center; justify-content:center;
font-size:19px; cursor:pointer; z-index:10001;
">🎛️</div>

<div id="icon-zoom-in" onclick="if(mapObject) mapObject.zoomIn()" title="Zoom avant" style="
position:fixed; top:calc(50% + 38px); left:15px; width:44px; height:44px; background:white; border-radius:50%;
box-shadow:0 3px 10px rgba(0,0,0,0.25); display:flex; align-items:center; justify-content:center;
font-size:20px; font-weight:bold; cursor:pointer; z-index:10001; color:#2D3277;
">+</div>

<div id="icon-zoom-out" onclick="if(mapObject) mapObject.zoomOut()" title="Zoom arrière" style="
position:fixed; top:calc(50% + 98px); left:15px; width:44px; height:44px; background:white; border-radius:50%;
box-shadow:0 3px 10px rgba(0,0,0,0.25); display:flex; align-items:center; justify-content:center;
font-size:20px; font-weight:bold; cursor:pointer; z-index:10001; color:#2D3277;
">-</div>

<div id="filiere-bar" style="
position:fixed; top:15px; left:68px; max-width: calc(100vw - 100px);
background:white; padding:10px 15px; border-radius:8px; z-index:9999;
box-shadow:0 3px 10px rgba(0,0,0,0.2); font-family:Arial,sans-serif;
display:flex; flex-wrap:nowrap; gap:6px; align-items:center; overflow-x:auto;
">
    <span style="font-weight:bold; font-size:13px; color:#2D3277; margin-right:5px; flex-shrink:0;">Filière :</span>
    {html_boutons_filiere}
</div>

<div id="panel-search" style="
display:none; position:fixed; top:calc(50% - 82px); left:68px; width:260px;
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
display:none; position:fixed; top:calc(50% - 22px); left:68px; width:280px; max-height: calc(50vh - 30px);
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
        <div id="accordion-tailles" style="display:none; padding-bottom:10px;">{html_checkbox_tailles}</div>
    </div>

    <div class="accordion-section" style="margin-bottom:4px;">
        <div onclick="toggleAccordion('accordion-trls')" style="display:flex; justify-content:space-between; align-items:center; cursor:pointer; padding:6px 0;">
            <span style="font-weight:bold; font-size:12px; color:#444;">Échelle TRL</span>
            <span id="accordion-trls-arrow" style="font-size:11px; color:#2D3277; transition:transform 0.2s ease;">▾</span>
        </div>
        <div id="accordion-trls" style="display:none; padding-bottom:5px;">{html_checkbox_trls}</div>
    </div>
</div>

<div id="logo-innova" style="
position:fixed; bottom:15px; left:15px; z-index:9999; background:#2D3277;
padding:10px 16px; border-radius:8px; box-shadow:0 3px 12px rgba(0,0,0,0.25);
display:flex; align-items:center;
">
    <img src="https://www.innov-a.com/wp-content/themes/skin/assets/images/svg/innov-a_blanc.svg" style="height:26px; display:block;" alt="Innov'A" />
</div>

<div id="legend-cartouche" style="
position:fixed; bottom:20px; right:20px; background:rgba(255,255,255,0.92);
padding:10px 15px; border-radius:8px; z-index:9999; box-shadow:0 3px 12px rgba(0,0,0,0.2);
font-family:Arial,sans-serif; max-width:80vw; backdrop-filter:blur(4px);
">
    <div style="font-weight:bold; font-size:11px; color:#2D3277; margin-bottom:6px; border-bottom:1px solid #DDD; padding-bottom:3px;">
         Légende des structures
    </div>
    <div style="display:flex; flex-direction:row; flex-wrap:wrap; gap:12px; align-items:center;">
        {html_legende_items}
    </div>
</div>

<div id="sidebar" style="
position:fixed; top:0; right:-720px; width:720px; height:100%; background:#F4F5F7;
z-index:99999; box-shadow:-5px 0 15px rgba(0,0,0,0.25); transition:right 0.4s ease;
overflow-y:auto; -webkit-overflow-scrolling:touch; font-family:Arial,sans-serif;
">
<button onclick="closeSidebar()" style="
position:absolute; top:10px; right:15px; background:white; border:1px solid #CCC;
border-radius:50%; width:36px; height:36px; font-size:22px; cursor:pointer; z-index:2000;
display:flex; align-items:center; justify-content:center; box-shadow:0 2px 6px rgba(0,0,0,0.2);
">×</button>
<div id="sidebar-container" style="min-height:100%; padding:20px 10px;"></div>
</div>

<div id="btn-dezoom" onclick="resetZoomHub()" style="
display:none; position:fixed; bottom:30px; left:calc(50% + 130px); transform:translateX(-50%);
background:#2D3277; color:white; padding:12px 22px; border-radius:30px; font-weight:bold;
font-size:14px; box-shadow:0 4px 12px rgba(0,0,0,0.3); cursor:pointer; z-index:9999;
">
⬅️ Revenir à la vue générale
</div>

<script>
var initialZoom = {INITIAL_ZOOM};
{js_content}
</script>
"""

m.get_root().html.add_child(folium.Element(ui_and_sidebar_html))

MAP_ANCRAGE = {
    "droite": "right",
    "bas": "bottom",
    "gauche": "left",
    "haut": "top",
}

def get_style_ancrage(actor, couleur):
    raw = get_text(actor, "Ancrage_label", "Ancrage_Label", default="haut")
    if isinstance(raw, list):
        raw = raw[0] if raw else "haut"
    val = str(raw).strip().lower()
    if not val:
        val = "haut"
    direction = MAP_ANCRAGE.get(val, "top")
    
    if direction == "bottom":
        label_pos = "top: 10px; left: 50%; transform: translateX(-50%); flex-direction: column-reverse;"
        arrow_style = f"border-left:5px solid transparent; border-right:5px solid transparent; border-bottom:7px solid {couleur};"
    elif direction == "left":
        label_pos = "right: 10px; top: 50%; transform: translateY(-50%); flex-direction: row;"
        arrow_style = f"border-top:5px solid transparent; border-bottom:5px solid transparent; border-left:7px solid {couleur};"
    elif direction == "right":
        label_pos = "left: 10px; top: 50%; transform: translateY(-50%); flex-direction: row-reverse;"
        arrow_style = f"border-top:5px solid transparent; border-bottom:5px solid transparent; border-right:7px solid {couleur};"
    else:
        label_pos = "bottom: 10px; left: 50%; transform: translateX(-50%); flex-direction: column;"
        arrow_style = f"border-left:5px solid transparent; border-right:5px solid transparent; border-top:7px solid {couleur};"
        
    return label_pos, arrow_style
    
acteurs_par_gps = defaultdict(list)

for idx, actor in enumerate(acteurs):
    coords = parse_gps(get_text(actor, "GPS"))
    if coords:
        acteurs_par_gps[coords].append((idx, actor))

for group_id, (coords, groupe) in enumerate(acteurs_par_gps.items()):

    def est_acteur_ensemble(item):
        act_fields = item[1]
        type_fiche = get_text(act_fields, "type_fiche", "Type_fiche", "Type").strip().lower()
        return type_fiche == "ensemble de projets"

    groupe.sort(key=lambda x: 0 if est_acteur_ensemble(x) else 1)
    nb_dependants = len(groupe) - 1

    for pos_in_group, (idx, actor) in enumerate(groupe):
        rec_id = actor.get("_record_id", f"rec_{idx}")
        is_host_attr = "true" if (pos_in_group == 0 and nb_dependants > 0) else "false"
        
        nom_brut = get_text(actor, "Nom", default="Sans nom")
        nom_court, nom_detail = parse_nom(nom_brut)

        taille = get_text(actor, "Taille", default="Autre")
        couleur = get_couleur(taille)
        domaine = get_text(actor, "Domaine", default="SANTÉ")

        sous_thematiques_brut = get_text(actor, "Subthema", "Sous-thématiques", "Sous-thematiques", "Sous-thématique")
        colonne_autre = get_text(actor, "Autre")
        sous_thematiques = colonne_autre if (not sous_thematiques_brut or sous_thematiques_brut.lower() == "autre") and colonne_autre else (sous_thematiques_brut or "Autre")

        icone_sous_thematiques = get_text(actor, "Icône", "Icone", default="🏷️")
        chapeau = get_text(actor, "Accroche")
        chiffre_cle = get_text(actor, "Faits")
        description = get_rich_text_html(actor, "Résumé long")
        elements_add = get_rich_text_html(actor, "Elements_add")
        equipements = get_rich_text_html(actor, "Equipement", "Equipements", "Équipement")

        email = get_text(actor, "Contacts", "Contact", "Email", default="")
        adresse = get_text(actor, "Adresse", default="")
        site_web = format_url(get_text(actor, "Website", "Site Web", "Site_web", default=""))
        url_interview = format_url(get_text(actor, "ITW", "Interview", default=""))

        logo_url = download_airtable_image(rec_id, actor.get("Logo"), prefix="logo")
        photo_url = download_airtable_image(rec_id, actor.get("Main illustration"), prefix="main")

        bloc_photo = f'<img src="{photo_url}" style="width:100%; height:100%; object-fit:cover; display:block;" />' if photo_url else '<div style="background:#EAEAEA; display:flex; justify-content:center; align-items:center; color:#666; font-size:18px; font-weight:bold; height:100%; min-height:100%;">PHOTO</div>'
        bloc_logo = f'<img src="{logo_url}" style="max-width:165px; max-height:75px; object-fit:contain;" />' if logo_url else 'LOGO'

        video_raw = actor.get("Video") or actor.get("Vidéo") or actor.get("Lien_video")
        second_illu_raw = actor.get("Second_illustration") or actor.get("SecondIllustration") or actor.get("Illustration_secondaire") or actor.get("Second illustration")
        media_url, media_type = get_media_url_and_type(rec_id, video_raw, second_illu_raw)

        if media_type in ["youtube", "vimeo"]:
            bloc_image_secondaire = f'<div style="width:100%; border-top:2px solid #E5E5E5; background:#F8F8F8; padding:0; position:relative; padding-bottom:56.25%; height:0; overflow:hidden;"><iframe src="{media_url}" style="position:absolute; top:0; left:0; width:100%; height:100%; border:0;" allowfullscreen></iframe></div>'
        elif media_type == "video":
            bloc_image_secondaire = f'<div style="width:100%; border-top:2px solid #E5E5E5; background:#111; padding:10px; text-align:center;"><video controls preload="metadata" style="width:100%; max-height:250px; display:block; margin:0 auto; background:black;"><source src="{media_url}" type="video/mp4">Votre navigateur ne prend pas en charge la lecture de vidéos.</video></div>'
        elif media_type == "image":
            bloc_image_secondaire = f'<div style="width:100%; border-top:2px solid #E5E5E5; background:#F8F8F8; padding:0; overflow:hidden;"><img src="{media_url}" style="width:100%; max-height:200px; object-fit:cover; display:block;" /></div>'
        else:
            bloc_image_secondaire = ""

        bouton_equipement_html = f"""
        <div style="position:relative; display:block; margin-bottom:10px;" class="tooltip-container">
            <button onclick="togglePopupInfo(event, this)" style="width:100%; background:#2D3277; color:white; border:none; border-radius:6px; padding:10px; font-weight:bold; cursor:pointer;">⚙️ Ressources ou équipements mobilisables</button>
            <div style="display:none; position:absolute; bottom:110%; right:0; background:#2C3E50; color:#fff; padding:12px; border-radius:6px; font-size:11px; z-index:9999; box-shadow:0 4px 12px rgba(0,0,0,0.3); line-height:1.4;" class="tooltip-text">
                <strong style="display:block; margin-bottom:5px; border-bottom:1px solid rgba(255,255,255,0.2); padding-bottom:3px;">Équipements mobilisables :</strong>
                {equipements}
            </div>
        </div>
        """ if equipements else ""

        bouton_info_html = f"""
        <div style="position:relative; display:block;" class="tooltip-container">
            <button onclick="togglePopupInfo(event, this)" style="width:100%; background:{couleur}; color:white; border:none; border-radius:6px; padding:10px; font-weight:bold; cursor:pointer;">➕ INFO</button>
            <div style="display:none; position:absolute; bottom:110%; right:0; background:#2C3E50; color:#fff; padding:12px; border-radius:6px; font-size:11px; z-index:9999; box-shadow:0 4px 12px rgba(0,0,0,0.3); line-height:1.4;" class="tooltip-text">
                <strong style="display:block; margin-bottom:5px; border-bottom:1px solid rgba(255,255,255,0.2); padding-bottom:3px;">Informations complémentaires :</strong>
                {elements_add}
            </div>
        </div>
        """ if elements_add else ""

        if MODE == "adherent":
            bloc_contact_html = (
                f'<a href="mailto:{email}" style="color:#2D3277; font-weight:bold; text-decoration:none;">{email}</a>'
                if email and "@" in email
                else (email or '<span style="color:#999; font-style:italic;">Non renseigné</span>')
            )
        else:
            sujet_encode = quote(CONTACT_PUBLIC_SUJET)
            corps_encode = quote(f"Bonjour,\n\nJe souhaite entrer en contact avec : {nom_court}.\n\n")
            mailto_public = f"mailto:{CONTACT_PUBLIC_EMAIL}?subject={sujet_encode}&body={corps_encode}"
            bloc_contact_html = f'<a href="{mailto_public}" style="color:#2D3277; font-weight:bold; text-decoration:none;">Nous contacter</a>'

        bloc_adresse_html = adresse.replace('\n', '<br>') if adresse else '<span style="color:#999; font-style:italic;">Non renseignée</span>'

        bouton_site_web_html = f'<a href="{site_web}" target="_blank" rel="noopener noreferrer" style="text-decoration:none;"><button style="width:100%; background:black; color:white; border:none; border-radius:6px; padding:9px; font-weight:bold; cursor:pointer; margin-bottom:10px;">🌐 SITE WEB</button></a>' if site_web else ""
        bouton_interview_html = f'<a href="{url_interview}" target="_blank" rel="noopener noreferrer" style="text-decoration:none;"><button style="width:100%; background:#2D3277; color:white; border:none; border-radius:6px; padding:9px; font-weight:bold; cursor:pointer; margin-top:10px;">📝 PORTRAIT</button></a>' if url_interview else ""

        fiche_html = f"""
        <div id="fiche-acteur-{idx}" data-is-host="{is_host_attr}" style="display:none;">
            <div style="display:flex; flex-direction:column; width:100%;">
                <div class="fiche-grid" style="display:grid; grid-template-columns:35% 65%; min-height:570px;">
                    <div style="background:#EAEAEA; overflow:hidden; display:flex; flex-direction:column; min-height:180px;">{bloc_photo}</div>
                    <div style="padding:20px; position:relative;">
                        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:10px; gap:10px; flex-wrap:wrap;">
                            <div style="display:inline-block; background:{couleur}; color:white; padding:6px 14px; border-radius:6px; font-weight:bold; font-size:13px;">{domaine.upper()}</div>
                            <div style="width:165px; height:75px; border:1px dashed #CCC; display:flex; justify-content:center; align-items:center; flex-shrink:0;">{bloc_logo}</div>
                        </div>
                        
                        <h1 style="margin-top:10px; margin-bottom:6px; font-size:24px; color:#2C3E50; word-break:break-word;">{nom_brut}</h1>
                        
                        <div style="color:{couleur}; font-size:14px; font-weight:600; margin-bottom:12px; line-height:1.4;">
                            {icone_sous_thematiques} {sous_thematiques}<br>
                            | <span style="font-weight:normal; font-style:italic;">{taille}</span>
                        </div>
                        
                        <div style="font-size:14px; font-weight:700; line-height:1.3; margin-bottom:12px;">{chapeau}</div>
                        
                        <div class="fiche-description" style="column-count:2; column-gap:18px; font-size:12px; line-height:1.45; text-align:justify; height:200px; overflow-y:auto; margin-bottom:14px;">{description}</div>
                        
                        {f'<div style="border-top:1px solid #DDD; border-bottom:1px solid #DDD; padding:8px; text-align:center; font-size:14px; font-weight:bold; font-style:italic; margin-bottom:14px;">{chiffre_cle}</div>' if chiffre_cle else ''}
                        
                        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(140px, 1fr)); gap:12px;">
                            <div>
                                {bouton_site_web_html}
                                <div style="font-size:12px; font-weight:bold;">Contact</div>
                                <div style="font-size:12px; word-break:break-all; margin-bottom:8px;">{bloc_contact_html}</div>
                                <div style="font-size:12px; font-weight:bold;">Adresse</div>
                                <div style="font-size:12px; word-break:break-all;">{bloc_adresse_html}</div>
                            </div>
                            <div>
                                <div style="margin-bottom:0px;">
                                    {bouton_equipement_html}
                                    {bouton_info_html}
                                </div>
                                {bouton_interview_html}
                            </div>
                        </div>
                    </div>
                </div>
                {bloc_image_secondaire}
            </div>
        </div>
        """
        m.get_root().html.add_child(folium.Element(fiche_html))

    # --- MARQUEURS SUR LA CARTE ---
    hote_idx, hote_actor = groupe[0]
    nom_hote_court, nom_hote_detail = parse_nom(get_text(hote_actor, "Nom"))
    nom_hote_affiche = formater_nom_etiquette(hote_actor, nom_hote_court)
    
    couleur_hote = get_couleur(get_text(hote_actor, "Taille"))
    taille_hote = get_text(hote_actor, "Taille", default="").replace("\n", " ").replace("\r", "")
    trl_hote_attr = "|||".join(get_liste_trls_record(hote_actor))
    filiere_hote = "|||".join(get_liste_valeurs(hote_actor, "Filières", "Filiere", "Domaine") or ["Autre"])
    hub_class = f"hub-marker-{group_id}"

    if len(groupe) == 1 or nb_dependants <= 0:
        label_pos_h, arrow_style_h = get_style_ancrage(hote_actor, couleur_hote)
        marker_html = f"""
        <div class="marker-wrapper-host" data-actor-id="{hote_idx}" data-taille="{taille_hote}" data-trl="{trl_hote_attr}" data-filiere="{filiere_hote}" onclick="openSidebarSingle({hote_idx})" ontouchstart="openSidebarSingle({hote_idx}); event.stopPropagation();" title="{nom_hote_detail}" style="display:flex; position:relative; cursor:pointer;">
            <div style="position:absolute; top:0; left:0; width:14px; height:14px; background:{couleur_hote}; border:2px solid white; border-radius:50%; transform:translate(-50%, -50%); box-shadow:0 1px 3px rgba(0,0,0,0.4); z-index:2;"></div>
            <div style="position:absolute; {label_pos_h} display:flex; align-items:center; z-index:1;">
                <div style="background:{couleur_hote}; color:white; padding:5px 9px; border-radius:6px; font-size:12px; font-weight:bold; text-align:center; max-width:220px; white-space:nowrap; box-shadow:0 2px 5px rgba(0,0,0,0.3);">{nom_hote_affiche}</div>
                <div style="width:0; height:0; {arrow_style_h}"></div>
            </div>
        </div>
        """
        folium.Marker(location=coords, icon=folium.DivIcon(html=marker_html, icon_size=(0, 0))).add_to(m)

    else:
        label_pos_hub, arrow_style_hub = get_style_ancrage(hote_actor, couleur_hote)

        marker_hub_html = f"""
        <div class="marker-wrapper-host {hub_class}" data-actor-id="{hote_idx}" data-group-id="{group_id}" data-taille="{taille_hote}" data-trl="{trl_hote_attr}" data-filiere="{filiere_hote}" onclick="handleHubClick({coords[0]}, {coords[1]}, '{hub_class}', {hote_idx})" ontouchstart="handleHubClick({coords[0]}, {coords[1]}, '{hub_class}', {hote_idx}); event.stopPropagation();" title="Hôte : {nom_hote_detail} (+{nb_dependants} projets)" style="display:flex; position:relative; cursor:pointer;">
            <div style="position:absolute; top:0; left:0; width:16px; height:16px; background:{couleur_hote}; border:3px solid white; border-radius:50%; box-shadow:0 0 6px rgba(0,0,0,0.4); transform:translate(-50%, -50%); z-index:2;"></div>
            <div style="position:absolute; {label_pos_hub} display:flex; align-items:center; z-index:1;">
                <div style="background:{couleur_hote}; color:white; padding:6px 12px; border-radius:8px; font-size:12px; font-weight:bold; text-align:center; max-width:260px; box-shadow:0 3px 8px rgba(0,0,0,0.4); border:2px solid #FFFFFF;">
                    <span style="display:inline-block; line-height:1.3; white-space:nowrap;">{nom_hote_affiche}</span>
                    <div style="margin-top:4px;">
                        <span style="background:#FFF; color:{couleur_hote}; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:900; display:inline-block;">+{nb_dependants}</span>
                    </div>
                </div>
                <div style="width:0; height:0; {arrow_style_hub}"></div>
            </div>
        </div>
        """
        folium.Marker(location=coords, icon=folium.DivIcon(html=marker_hub_html, icon_size=(0, 0))).add_to(m)

        for sub_i, (idx, actor) in enumerate(groupe):
            if sub_i == 0:
                continue

            nom_actor_court, nom_actor_detail = parse_nom(get_text(actor, "Nom"))
            nom_actor_affiche = formater_nom_etiquette(actor, nom_actor_court)
            
            couleur_actor = get_couleur(get_text(actor, "Taille"))
            taille_actor = get_text(actor, "Taille", default="").replace("\n", " ").replace("\r", "")
            trl_actor_attr = "|||".join(get_liste_trls_record(actor))
            filiere_actor = "|||".join(get_liste_valeurs(actor, "Filières", "Filiere", "Domaine") or ["Autre"])

            coords_second = parse_gps(get_text(actor, "GPS_second"))
            if not coords_second:
                coords_second = coords

            label_pos_s, arrow_style_s = get_style_ancrage(actor, couleur_actor)
            sub_marker_html = f"""
            <div class="marker-wrapper marker-wrapper-sub sub-{hub_class}" data-actor-id="{idx}" data-taille="{taille_actor}" data-trl="{trl_actor_attr}" data-filiere="{filiere_actor}" data-lat="{coords_second[0]}" data-lng="{coords_second[1]}" onclick="openSidebarSingle({idx})" ontouchstart="openSidebarSingle({idx}); event.stopPropagation();" title="{nom_actor_detail}" style="display:none; position:relative; cursor:pointer; z-index:10000;">
                <div style="position:absolute; top:0; left:0; width:12px; height:12px; background:{couleur_actor}; border:2px solid white; border-radius:50%; transform:translate(-50%, -50%); z-index:2;"></div>
                <div style="position:absolute; {label_pos_s} display:flex; align-items:center; z-index:1;">
                    <div style="background:{couleur_actor}; color:white; padding:5px 9px; border-radius:6px; font-size:11px; font-weight:bold; text-align:center; max-width:200px; white-space:nowrap; box-shadow:0 2px 6px rgba(0,0,0,0.35); border:1px solid white;">{nom_actor_affiche}</div>
                    <div style="width:0; height:0; {arrow_style_s}"></div>
                </div>
            </div>
            """
            folium.Marker(location=coords_second, icon=folium.DivIcon(html=sub_marker_html, icon_size=(0, 0))).add_to(m)

nom_fichier = f"carte_{MODE}.html"
m.save(nom_fichier)
print(f"✅ Carte exportée : {nom_fichier} (mode = '{MODE}')")

m.save("index.html")
print("✅ Carte exportée : index.html (pour la racine GitHub Pages)")
