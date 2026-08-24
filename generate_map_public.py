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
# 1. CONFIGURATION
WORKER_URL = "https://flat-forest-26c8.charlottepiau-innova.workers.dev/"
TABLE = "Cartographie"
MODE = "public"
CONTACT_PUBLIC_EMAIL = "contact@innov-a.com"
CONTACT_PUBLIC_SUJET = "Demande de mise en relation"

# Dossier d'accueil des images
os.makedirs("assets/images", exist_ok=True)

# 2. RÉCUPÉRATION DES DONNÉES DEPUIS CLOUDFLARE
response = requests.get(WORKER_URL)
data = response.json()
records = data.get("records", [])

# 3. TRAITEMENT DES DONNÉES ET GÉNÉRATION DE LA CARTE
for record in records:
    fields = record.get("fields", {})
    record_id = record.get("id")
    
    # GESTION DU LOGO / IMAGE
    img_src = ""
    attachments = fields.get("Logo", []) # Vérifie le nom exact de ta colonne
    
    if attachments:
        airtable_img_url = attachments[0].get("url")
        # Récupérer l'extension d'origine (.png, .jpg, etc.)
        filename = attachments[0].get("filename", "")
        ext = filename.split(".")[-1] if "." in filename else "png"
        
        local_path = f"assets/images/{record_id}.{ext}"
        
        # Téléchargement local
        try:
            img_res = requests.get(airtable_img_url, timeout=10)
            if img_res.status_code == 200:
                with open(local_path, "wb") as f:
                    f.write(img_res.content)
                img_src = local_path # Utilisé ensuite dans le HTML de la popup
        except Exception as e:
            print(f"Erreur téléchargement {record_id}: {e}")
            
# ==================================
# 1. CONFIGURATION COULEURS
# ==================================

COULEURS = {
    "Etablissement médical":                        "#2D3277", #bleu marine
    "Etablissement de formation":                    "#845EC2", #violet
    "Laboratoire ou activité de recherche":          "#FBC9D4", #rose pâle
    "Plateforme technologique ou centre technique": "#FB6F92", #rose
    "Structure d'accompagnement à l'innovation":    "#FDC500", #jaune
    "Start-up ou TPE":                              "#9BC045", #vert
    "PME et entreprises":                           "#00EBF5", #bleu ciel
    "Association":                                  "#FFC27F", #orange pâle
    "Projet collaboratif":                          "#E8873A", #orange
    "Autre":                                        "#888888", #gris
}

def get_couleur(taille_valeur):
    if not taille_valeur:
        return COULEURS["Autre"]
    val_str = str(taille_valeur).strip().replace("\n", " ").replace("\r", "")
    if val_str in COULEURS:
        return COULEURS[val_str]
    for nom_taille, couleur in COULEURS.items():
        if nom_taille.lower() in val_str.lower():
            return couleur
    return COULEURS["Autre"]


# ==================================
# 2. RECUPERATION ET PARSING WORKER
# ==================================
def fetch_acteurs():
    records, offset = [], None
    while True:
        params = {"pageSize": 100}
        if offset:
            params["offset"] = offset
        
        # Appel vers le Worker Cloudflare
        res = requests.get(WORKER_URL, params=params)
        res.raise_for_status()
        
        data = res.json()
        records += [r["fields"] for r in data.get("records", [])]
        
        # Gestion de la pagination pour la page suivante
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
            val_str = str(val).strip().replace("\n", " ").replace("\r", "")
            if val_str:
                return val_str
    return default

def get_rich_text_html(record, *keys, default=""):
    """
    Comme get_text, mais conserve les sauts de ligne (nécessaires pour le Markdown Airtable)
    et convertit le résultat en HTML.
    """
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
                return markdown.markdown(val_str, extensions=["nl2br"])
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

def get_image_url(field_value):
    if not field_value:
        return ""
    if isinstance(field_value, list) and len(field_value) > 0:
        if isinstance(field_value[0], dict):
            return field_value[0].get("url", "")
        return str(field_value[0])
    match = re.search(r"\((https://[^)]+)\)", str(field_value))
    if match:
        return match.group(1)
    if str(field_value).startswith("http"):
        return str(field_value)
    return ""

def get_media_url_and_type(video_field, second_illu):
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
        img_url = ""
        if isinstance(second_illu, list) and len(second_illu) > 0:
            if isinstance(second_illu[0], dict):
                img_url = second_illu[0].get("url", "")
            else:
                img_url = str(second_illu[0])
        else:
            match = re.search(r"\((https://[^)]+)\)", str(second_illu))
            img_url = match.group(1) if match else str(second_illu)
        img_url = img_url.strip()
        if img_url.startswith("http"):
            return img_url, "image"
    return "", ""

def parse_gps(gps_str):
    if not gps_str:
        return None
    match = re.match(r"([\d.-]+),\s*([\d.-]+)", str(gps_str).strip())
    if match:
        return round(float(match.group(1)), 5), round(float(match.group(2)), 5)
    return None

# ==================================
# 3. COLLECTE DES VALEURS UNIQUES
# ==================================

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
# ==================================
# 4. INITIALISATION CARTE & UI
# ==================================

INITIAL_ZOOM = 14
m = folium.Map(location=[49.89, 2.30], zoom_start=INITIAL_ZOOM, tiles="CartoDB Positron")

html_checkbox_tailles = "".join([
    f'<label style="display:flex; align-items:center; gap:8px; font-size:12px; margin-bottom:5px; cursor:pointer;">'
    f'<input type="checkbox" class="filter-checkbox filter-taille" value="{t}" checked onchange="applyFilters()"> {t}</label>'
    for t in liste_tailles_presentes
])

html_legende_items = "".join([
    f'<div style="display:flex; align-items:center; gap:8px; margin-bottom:5px; font-size:11px; color:#333;">'
    f'<div style="width:12px; height:12px; background:{COULEURS[t]}; border-radius:3px; flex-shrink:0; border:1px solid rgba(0,0,0,0.1);"></div>'
    f'<span>{t}</span></div>'
    for t in liste_tailles_presentes
])

html_checkbox_trls = "".join([
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
<style>
.fiche-description p { margin:0 0 6px 0; }
.fiche-description ul, .fiche-description ol { margin:2px 0 8px 0; padding-left:16px; break-inside:avoid-column; }
.fiche-description li { margin-bottom:2px; }
.fiche-description strong { color:#2C3E50; }
.tooltip-text p { margin:0 0 6px 0; }
.tooltip-text ul, .tooltip-text ol { margin:2px 0 8px 0; padding-left:18px; }
.tooltip-text li { margin-bottom:3px; }
</style>

<!-- ICONES DECLENCHEURS (recherche / filtres) -->
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

<!-- BARRE FILIERE - toujours visible -->
<div id="filiere-bar" style="
position:fixed; top:15px; left:68px; max-width: calc(100vw - 100px);
background:white; padding:10px 15px; border-radius:8px; z-index:9999;
box-shadow:0 3px 10px rgba(0,0,0,0.2); font-family:Arial,sans-serif;
display:flex; flex-wrap:wrap; gap:6px; align-items:center;
">
    <span style="font-weight:bold; font-size:13px; color:#2D3277; margin-right:5px;">Filière :</span>
    __HTML_BOUTONS_FILIERE__
</div>

<!-- PANNEAU RECHERCHE (masque par defaut) -->
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

<!-- PANNEAU FILTRES (masque par defaut) -->
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
        <div id="accordion-trls" style="display:none; padding-bottom:5px;">__HTML_CHECKBOX_TRLS__</div>
    </div>
</div>

<!-- LOGO INNOV'A -->
<div id="logo-innova" style="
position:fixed; bottom:15px; left:15px; z-index:9999; background:#2D3277;
padding:10px 16px; border-radius:8px; box-shadow:0 3px 12px rgba(0,0,0,0.25);
display:flex; align-items:center;
">
    <img src="https://www.innov-a.com/wp-content/themes/skin/assets/images/svg/innov-a_blanc.svg" style="height:26px; display:block;" alt="Innov'A" />
</div>

<div id="legend-cartouche" style="
position:fixed; bottom:20px; right:20px; background:rgba(255,255,255,0.92);
padding:12px 15px; border-radius:8px; z-index:9999; box-shadow:0 3px 12px rgba(0,0,0,0.2);
font-family:Arial,sans-serif; max-width:280px; backdrop-filter:blur(4px);
">
    <div style="font-weight:bold; font-size:12px; color:#2D3277; margin-bottom:8px; border-bottom:1px solid #DDD; padding-bottom:4px;">
        🎨 Légende des structures
    </div>
    __HTML_LEGENDE_ITEMS__
</div>

<div id="sidebar" style="
position:fixed; top:0; right:-720px; width:720px; height:100%; background:#F4F5F7;
z-index:99999; box-shadow:-5px 0 15px rgba(0,0,0,0.25); transition:right 0.4s ease;
overflow-y:auto; font-family:Arial,sans-serif;
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
var mapObject = null;
var initialZoom = __INITIAL_ZOOM__;

document.addEventListener("DOMContentLoaded", function() {
    for (var key in window) {
        if (key.startsWith("map_") && window[key] instanceof L.Map) {
            mapObject = window[key];
            break;
        }
    }
});

function cleanTaille(val) {
    return (val || '').replace(/\\n/g, ' ').replace(/\\r/g, '').trim().toLowerCase();
}

function toggleAccordion(contentId) {
    var content = document.getElementById(contentId);
    var arrow = document.getElementById(contentId + '-arrow');
    var isOpen = content.style.display === 'block';
    content.style.display = isOpen ? 'none' : 'block';
    if (arrow) arrow.style.transform = isOpen ? 'rotate(0deg)' : 'rotate(-180deg)';
}

function togglePanel(panelId, iconId) {
    var panel = document.getElementById(panelId);
    var isOpen = panel.style.display === 'block';
    // Ferme tous les panneaux avant d'ouvrir celui demande
    document.querySelectorAll('#panel-search, #panel-filter').forEach(function(p) {
        p.style.display = 'none';
    });
    panel.style.display = isOpen ? 'none' : 'block';
}

document.addEventListener('click', function(e) {
    var isPanel = e.target.closest('#panel-search, #panel-filter');
    var isIcon = e.target.closest('#icon-search-btn, #icon-filter-btn');
    if (!isPanel && !isIcon) {
        document.querySelectorAll('#panel-search, #panel-filter').forEach(function(p) {
            p.style.display = 'none';
        });
    }
});

var selectedFiliere = 'all';

function filterFiliere(filiere, btnEl) {
    selectedFiliere = filiere;
    document.querySelectorAll('#filiere-bar .filter-btn').forEach(function(btn) {
        btn.style.background = '#EAEAEA';
        btn.style.color = '#333';
    });
    btnEl.style.background = '#2D3277';
    btnEl.style.color = 'white';
    applyFilters();
}

function applyFilters() {
    var selectedTailles = Array.from(document.querySelectorAll('.filter-taille:checked'))
        .map(function(cb) { return cleanTaille(cb.value); });
    var selectedTrls = Array.from(document.querySelectorAll('.filter-trl:checked'))
        .map(function(cb) { return cb.value.trim().toLowerCase(); });
    
    var searchInputVal = document.getElementById('global-search-input');
    var searchQuery = searchInputVal ? searchInputVal.value.trim().toLowerCase() : "";

    function matchesSearch(actorId) {
        if (!searchQuery) return true;
        var ficheElem = document.getElementById('fiche-acteur-' + actorId);
        if (!ficheElem) return false;
        return ficheElem.innerText.toLowerCase().indexOf(searchQuery) !== -1;
    }

    function matchesFiliere(el) {
        if (selectedFiliere === 'all') return true;
        var vals = (el.getAttribute('data-filiere') || '').split('|||').map(function(s) { return s.trim(); });
        return vals.indexOf(selectedFiliere) !== -1;
    }

    // Traitement par groupe (Hôte + ses dépendants)
    document.querySelectorAll('.marker-wrapper-host').forEach(function(hostEl) {
        if (hostEl.getAttribute('data-hub-opened') === 'true') return;

        var hubClass = Array.from(hostEl.classList).find(function(c) { return c.startsWith('hub-marker-'); });
        var rawTaille = cleanTaille(hostEl.getAttribute('data-taille'));
        var elTrlsList = (hostEl.getAttribute('data-trl') || '').toLowerCase()
                         .split('|||').map(function(s) { return s.trim(); });
        var actorId = hostEl.getAttribute('data-actor-id');

        var matchTaille = selectedTailles.indexOf(rawTaille) !== -1;
        var matchTrl = elTrlsList.length === 0 || elTrlsList.some(function(trl) {
            return trl === '' || selectedTrls.indexOf(trl) !== -1;
        });
        var matchSearch = matchesSearch(actorId);
        var matchFiliere = matchesFiliere(hostEl);

        var hostVisible = (matchTaille && matchTrl && matchSearch && matchFiliere);
        hostEl.style.display = hostVisible ? 'flex' : 'none';

        // Gérer uniquement les sous-marqueurs de CET hôte spécifique
        if (hubClass) {
            document.querySelectorAll('.sub-' + hubClass).forEach(function(subEl) {
                var subRawTaille = cleanTaille(subEl.getAttribute('data-taille'));
                var subElTrlsList = (subEl.getAttribute('data-trl') || '').toLowerCase()
                                 .split('|||').map(function(s) { return s.trim(); });
                var subActorId = subEl.getAttribute('data-actor-id');

                var subMatchTaille = selectedTailles.indexOf(subRawTaille) !== -1;
                var subMatchTrl = subElTrlsList.length === 0 || subElTrlsList.some(function(trl) {
                    return trl === '' || selectedTrls.indexOf(trl) !== -1;
                });
                var subMatchSearch = matchesSearch(subActorId);
                var subMatchFiliere = matchesFiliere(subEl);

                // Affiche les dépendances de cet hôte uniquement si l'hôte est masqué ET que le dépendant passe ses filtres
                var shouldShow = (!hostVisible || searchQuery) && subMatchTaille && subMatchTrl && subMatchSearch && subMatchFiliere;
                subEl.style.display = shouldShow ? 'flex' : 'none';
            });
        }
    });

    // Cas des marqueurs hôtes isolés (sans sous-marqueurs)
    document.querySelectorAll('.marker-wrapper-host:not([class*="hub-marker-"])').forEach(function(el) {
        if (el.getAttribute('data-hub-opened') === 'true') return;
        var rawTaille = cleanTaille(el.getAttribute('data-taille'));
        var elTrlsList = (el.getAttribute('data-trl') || '').toLowerCase()
                         .split('|||').map(function(s) { return s.trim(); });
        var actorId = el.getAttribute('data-actor-id');

        var matchTaille = selectedTailles.indexOf(rawTaille) !== -1;
        var matchTrl = elTrlsList.length === 0 || elTrlsList.some(function(trl) {
            return trl === '' || selectedTrls.indexOf(trl) !== -1;
        });
        var matchSearch = matchesSearch(actorId);
        var matchFiliere = matchesFiliere(el);

        el.style.display = (matchTaille && matchTrl && matchSearch && matchFiliere) ? 'flex' : 'none';
    });
}

function fitGroupToVisible(hubClass, hoteLat, hoteLng) {
    if (!mapObject) return;
    var pts = [[hoteLat, hoteLng]];
    document.querySelectorAll('.sub-' + hubClass).forEach(function(el) {
        var la = parseFloat(el.getAttribute('data-lat'));
        var lo = parseFloat(el.getAttribute('data-lng'));
        if (!isNaN(la) && !isNaN(lo)) pts.push([la, lo]);
    });

    var sidebarEl = document.getElementById('sidebar');
    var sidebarWidth = sidebarEl ? sidebarEl.offsetWidth : 0;

    // fitBounds englobe l'hote + tous ses dependants (meme s'ils sont
    // actuellement masques par un filtre), avec une marge qui reserve
    // la place de la fiche a droite et des icones/de la barre filiere en haut,
    // et un zoom maximal pour ne pas trop serrer si un seul point.
    mapObject.flyToBounds(L.latLngBounds(pts), {
        paddingTopLeft: [70, 140],
        paddingBottomRight: [sidebarWidth + 50, 70],
        maxZoom: 17,
        animate: true,
        duration: 1.2
    });
}

function handleHubClick(lat, lng, hubClass, hoteId) {
    if (!mapObject) return;
    fitGroupToVisible(hubClass, lat, lng);

    var mainMarker = document.querySelector('.' + hubClass);
    if (mainMarker) {
        mainMarker.style.display = 'none';
        mainMarker.setAttribute('data-hub-opened', 'true');
    }

    if (hoteId !== undefined && hoteId !== null) {
        openSidebarSingle(hoteId);
    }

    var selectedTailles = Array.from(document.querySelectorAll('.filter-taille:checked'))
        .map(function(cb) { return cleanTaille(cb.value); });
    var selectedTrls = Array.from(document.querySelectorAll('.filter-trl:checked'))
        .map(function(cb) { return cb.value.trim().toLowerCase(); });
    
    var searchInputVal = document.getElementById('global-search-input');
    var searchQuery = searchInputVal ? searchInputVal.value.trim().toLowerCase() : "";

    function matchesSearch(actorId) {
        if (!searchQuery) return true;
        var ficheElem = document.getElementById('fiche-acteur-' + actorId);
        if (!ficheElem) return false;
        return ficheElem.innerText.toLowerCase().indexOf(searchQuery) !== -1;
    }

    function matchesFiliere(el) {
        if (selectedFiliere === 'all') return true;
        var vals = (el.getAttribute('data-filiere') || '').split('|||').map(function(s) { return s.trim(); });
        return vals.indexOf(selectedFiliere) !== -1;
    }

    document.querySelectorAll('.sub-' + hubClass).forEach(function(el) {
        el.setAttribute('data-active-hub', 'true');

        var rawTaille = cleanTaille(el.getAttribute('data-taille'));
        var elTrlsList = (el.getAttribute('data-trl') || '').toLowerCase()
                         .split('|||').map(function(s) { return s.trim(); });
        var actorId = el.getAttribute('data-actor-id');

        var matchTaille = selectedTailles.indexOf(rawTaille) !== -1;
        var matchTrl = elTrlsList.length === 0 || elTrlsList.some(function(trl) {
            return trl === '' || selectedTrls.indexOf(trl) !== -1;
        });
        var matchSearch = matchesSearch(actorId);
        var matchFiliere = matchesFiliere(el);

        el.style.display = (matchTaille && matchTrl && matchSearch && matchFiliere) ? 'flex' : 'none';
    });

    document.getElementById('btn-dezoom').style.display = 'block';
}

function resetZoomHub() {
    if (!mapObject) return;
    mapObject.flyTo([49.89, 2.30], initialZoom, { animate: true, duration: 1.0 });

    document.querySelectorAll('.marker-wrapper-host').forEach(function(el) {
        el.removeAttribute('data-hub-opened');
    });
    document.querySelectorAll('.marker-wrapper-sub').forEach(function(el) {
        el.style.display = 'none';
        el.removeAttribute('data-active-hub');
    });

    applyFilters();
    document.getElementById('btn-dezoom').style.display = 'none';
}

function togglePopupInfo(event, btnElement) {
    event.stopPropagation();
    var container = btnElement.closest('.tooltip-container');
    var popup = container.querySelector('.tooltip-text');
    document.querySelectorAll('.tooltip-text').forEach(function(p) {
        if (p !== popup) p.style.display = 'none';
    });
    popup.style.display = (popup.style.display === 'block') ? 'none' : 'block';
}

document.addEventListener('click', function(e) {
    if (!e.target.closest('.tooltip-container')) {
        document.querySelectorAll('.tooltip-text').forEach(function(popup) {
            popup.style.display = 'none';
        });
    }
});

function openSidebarSingle(id) {
    var container = document.getElementById('sidebar-container');
    container.innerHTML = '';
    var elem = document.getElementById('fiche-acteur-' + id);
    if (elem) {
        var wrapper = document.createElement('div');
        wrapper.style.cssText = "margin-bottom:25px; background:#FFF; border-radius:8px; box-shadow:0 3px 10px rgba(0,0,0,0.1); overflow:hidden;";
        var contentNode = elem.cloneNode(true);
        contentNode.style.display = 'block';
        wrapper.appendChild(contentNode);
        container.appendChild(wrapper);
    }
    document.getElementById('sidebar').style.right = '0px';
}

function closeSidebar() {
    document.getElementById('sidebar').style.right = '-720px';
}
</script>
"""

ui_and_sidebar_html = ui_and_sidebar_html.replace("__HTML_CHECKBOX_TAILLES__", html_checkbox_tailles)
ui_and_sidebar_html = ui_and_sidebar_html.replace("__HTML_CHECKBOX_TRLS__", html_checkbox_trls)
ui_and_sidebar_html = ui_and_sidebar_html.replace("__HTML_LEGENDE_ITEMS__", html_legende_items)
ui_and_sidebar_html = ui_and_sidebar_html.replace("__HTML_BOUTONS_FILIERE__", html_boutons_filiere)
ui_and_sidebar_html = ui_and_sidebar_html.replace("__INITIAL_ZOOM__", str(INITIAL_ZOOM))

m.get_root().html.add_child(folium.Element(ui_and_sidebar_html))

# ==================================
# 5. REGROUPEMENT PAR GPS & GENERATION
# ==================================
# Affiche les valeurs réelles lues dans votre base Airtable pour debug
print("Valeurs Ancrage_label détectées :", set(get_text(a, "Ancrage_label", "Ancrage_Label") for a in acteurs))

MAP_ANCRAGE = {
    "droite": "right",
    "bas": "bottom",
    "gauche": "left",
    "haut": "top",
}

def get_style_ancrage(actor, couleur):
    # Récupération de la valeur (si vide ou absente -> 'haut')
    raw = get_text(actor, "Ancrage_label", "Ancrage_Label", default="haut")
    if isinstance(raw, list):
        raw = raw[0] if raw else "haut"
    
    val = str(raw).strip().lower()
    
    # Si la case est vide (''), on force 'haut' par défaut
    if not val:
        val = "haut"
        
    direction = MAP_ANCRAGE.get(val, "top")
    
    if direction == "bottom":
        # Bas : étiquette sous le point GPS
        label_pos = "top: 10px; left: 50%; transform: translateX(-50%); flex-direction: column-reverse;"
        arrow_style = f"border-left:5px solid transparent; border-right:5px solid transparent; border-bottom:7px solid {couleur};"
        
    elif direction == "left":
        # Gauche : étiquette à gauche du point GPS
        label_pos = "right: 10px; top: 50%; transform: translateY(-50%); flex-direction: row;"
        arrow_style = f"border-top:5px solid transparent; border-bottom:5px solid transparent; border-left:7px solid {couleur};"
        
    elif direction == "right":
        # Droite : étiquette à droite du point GPS
        label_pos = "left: 10px; top: 50%; transform: translateY(-50%); flex-direction: row-reverse;"
        arrow_style = f"border-top:5px solid transparent; border-bottom:5px solid transparent; border-right:7px solid {couleur};"
        
    else:
        # Haut (par défaut si vide, 'haut', ou non renseigné)
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
        nom_act = get_text(act_fields, "Nom").lower()
        if type_fiche == "ensemble de projets":
            return True
        if any(h in nom_act for h in ["chu", "curs", "biolab"]):
            return True
        return False

    groupe.sort(key=lambda x: 0 if est_acteur_ensemble(x) else 1)
    nb_dependants = len(groupe) - 1

    # --- FICHES INDIVIDUELLES (SIDEBAR) ---
    for pos_in_group, (idx, actor) in enumerate(groupe):
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
        site_web = get_text(actor, "Website", "Site Web", default="#")
        url_interview = get_text(actor, "ITW", "Interview", default="#")

        logo_url = get_image_url(actor.get("Logo"))
        photo_url = get_image_url(actor.get("Main illustration"))

        bloc_photo = f'<img src="{photo_url}" style="width:100%; height:100%; object-fit:cover; display:block;" />' if photo_url else '<div style="background:#EAEAEA; display:flex; justify-content:center; align-items:center; color:#666; font-size:18px; font-weight:bold; height:100%; min-height:100%;">PHOTO</div>'
        bloc_logo = f'<img src="{logo_url}" style="max-width:110px; max-height:50px; object-fit:contain;" />' if logo_url else 'LOGO'

        video_raw = actor.get("Video") or actor.get("Vidéo") or actor.get("Lien_video")
        second_illu_raw = actor.get("Second_illustration") or actor.get("SecondIllustration") or actor.get("Illustration_secondaire") or actor.get("Second illustration")
        media_url, media_type = get_media_url_and_type(video_raw, second_illu_raw)

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
            <button onclick="togglePopupInfo(event, this)" style="width:100%; background:#2D3277; color:white; border:none; border-radius:6px; padding:10px; font-weight:bold; cursor:pointer;">⚙️ Équipements mobilisables</button>
            <div style="display:none; position:absolute; bottom:110%; left:0; width:260px; background:#2C3E50; color:#fff; padding:12px; border-radius:6px; font-size:11px; z-index:9999; box-shadow:0 4px 12px rgba(0,0,0,0.3); line-height:1.4;" class="tooltip-text">
                <strong style="display:block; margin-bottom:5px; border-bottom:1px solid rgba(255,255,255,0.2); padding-bottom:3px;">Équipements mobilisables :</strong>
                {equipements}
            </div>
        </div>
        """ if equipements else ""

        bouton_info_html = f"""
        <div style="position:relative; display:block;" class="tooltip-container">
            <button onclick="togglePopupInfo(event, this)" style="width:100%; background:{couleur}; color:white; border:none; border-radius:6px; padding:10px; font-weight:bold; cursor:pointer;">➕ INFO</button>
            <div style="display:none; position:absolute; bottom:110%; left:0; width:260px; background:#2C3E50; color:#fff; padding:12px; border-radius:6px; font-size:11px; z-index:9999; box-shadow:0 4px 12px rgba(0,0,0,0.3); line-height:1.4;" class="tooltip-text">
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
        bloc_adresse_html = adresse or '<span style="color:#999; font-style:italic;">Non renseignée</span>'

        fiche_html = f"""
        <div id="fiche-acteur-{idx}" data-is-host="{is_host_attr}" style="display:none;">
            <div style="display:flex; flex-direction:column; width:100%;">
                <div style="display:grid; grid-template-columns:35% 65%; min-height:570px; align-stretch;">
                    <div style="background:#EAEAEA; overflow:hidden; display:flex; flex-direction:column;">{bloc_photo}</div>
                    <div style="padding:20px; position:relative;">
                        <div style="display:inline-block; background:{couleur}; color:white; padding:6px 14px; border-radius:6px; font-weight:bold; font-size:13px;">{domaine.upper()}</div>
                        <div style="position:absolute; top:20px; right:20px; width:110px; height:50px; border:1px dashed #CCC; display:flex; justify-content:center; align-items:center;">{bloc_logo}</div>
                        <h1 style="margin-top:20px; margin-bottom:6px; font-size:30px; color:#2C3E50;" title="{nom_detail}">{nom_court}</h1>
                        <div style="color:{couleur}; font-size:15px; font-weight:600; margin-bottom:14px; line-height:1.4;">
                            {icone_sous_thematiques} {sous_thematiques}<br>
                            | <span style="font-weight:normal; font-style:italic;">{taille}</span>
                        </div>
                        <div style="font-size:15px; font-weight:700; line-height:1.3; margin-bottom:12px;">{chapeau}</div>
                        <div class="fiche-description" style="column-count:2; column-gap:18px; font-size:12px; line-height:1.45; text-align:justify; height:200px; overflow-y:auto; margin-bottom:14px;">{description}</div>
                        {f'<div style="border-top:1px solid #DDD; border-bottom:1px solid #DDD; padding:8px; text-align:center; font-size:15px; font-weight:bold; font-style:italic; margin-bottom:14px;">{chiffre_cle}</div>' if chiffre_cle else ''}
                        <div style="display:grid; grid-template-columns:50% 50%; gap:12px;">
                            <div>
                                {f'<a href="{site_web}" target="_blank" style="text-decoration:none;"><button style="width:100%; background:black; color:white; border:none; border-radius:6px; padding:9px; font-weight:bold; cursor:pointer; margin-bottom:10px;">🌐 SITE WEB</button></a>' if site_web not in ["#", ""] else ''}
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
                                {f'<a href="{url_interview}" target="_blank" style="text-decoration:none;"><button style="width:100%; background:#2D3277; color:white; border:none; border-radius:6px; padding:9px; font-weight:bold; cursor:pointer; margin-top:10px;">🎤 INTERVIEW</button></a>' if url_interview not in ["#", ""] else ''}
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
    couleur_hote = get_couleur(get_text(hote_actor, "Taille"))
    taille_hote = get_text(hote_actor, "Taille", default="").replace("\n", " ").replace("\r", "")
    trl_hote_attr = "|||".join(get_liste_trls_record(hote_actor))
    filiere_hote = "|||".join(get_liste_valeurs(hote_actor, "Filières", "Filiere", "Domaine") or ["Autre"])
    hub_class = f"hub-marker-{group_id}"

    if len(groupe) == 1 or nb_dependants <= 0:
        label_pos_h, arrow_style_h = get_style_ancrage(hote_actor, couleur_hote)
        marker_html = f"""
        <div class="marker-wrapper-host" data-actor-id="{hote_idx}" data-taille="{taille_hote}" data-trl="{trl_hote_attr}" data-filiere="{filiere_hote}" onclick="openSidebarSingle({hote_idx})" title="{nom_hote_detail}" style="display:flex; position:relative; cursor:pointer;">
            <div style="position:absolute; top:0; left:0; width:14px; height:14px; background:{couleur_hote}; border:2px solid white; border-radius:50%; transform:translate(-50%, -50%); box-shadow:0 1px 3px rgba(0,0,0,0.4); z-index:2;"></div>
            <div style="position:absolute; {label_pos_h} display:flex; align-items:center; z-index:1;">
                <div style="background:{couleur_hote}; color:white; padding:5px 9px; border-radius:6px; font-size:12px; font-weight:bold; text-align:center; white-space:normal; max-width:180px; box-shadow:0 2px 5px rgba(0,0,0,0.3);">{nom_hote_court}</div>
                <div style="width:0; height:0; {arrow_style_h}"></div>
            </div>
        </div>
        """
        folium.Marker(location=coords, icon=folium.DivIcon(html=marker_html, icon_size=(0, 0))).add_to(m)

    else:
        label_pos_hub, arrow_style_hub = get_style_ancrage(hote_actor, couleur_hote)
        marker_hub_html = f"""
        <div class="marker-wrapper-host {hub_class}" data-actor-id="{hote_idx}" data-group-id="{group_id}" data-taille="{taille_hote}" data-trl="{trl_hote_attr}" data-filiere="{filiere_hote}" onclick="handleHubClick({coords[0]}, {coords[1]}, '{hub_class}', {hote_idx})" title="Hôte : {nom_hote_detail} (+{nb_dependants} projets)" style="display:flex; position:relative; cursor:pointer;">
            <div style="position:absolute; top:0; left:0; width:16px; height:16px; background:{couleur_hote}; border:3px solid white; border-radius:50%; box-shadow:0 0 6px rgba(0,0,0,0.4); transform:translate(-50%, -50%); z-index:2;"></div>
            <div style="position:absolute; {label_pos_hub} display:flex; align-items:center; z-index:1;">
                <div style="background:{couleur_hote}; color:white; padding:6px 10px; border-radius:8px; font-size:12px; font-weight:bold; text-align:center; white-space:normal; max-width:180px; box-shadow:0 3px 8px rgba(0,0,0,0.4); border:2px solid #FFFFFF;">
                    🏢 {nom_hote_court}
                    <span style="background:#FFF; color:{couleur_hote}; padding:2px 7px; border-radius:10px; font-size:11px; margin-left:5px; font-weight:900;">+{nb_dependants}</span>
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
            couleur_actor = get_couleur(get_text(actor, "Taille"))
            taille_actor = get_text(actor, "Taille", default="").replace("\n", " ").replace("\r", "")
            trl_actor_attr = "|||".join(get_liste_trls_record(actor))
            filiere_actor = "|||".join(get_liste_valeurs(actor, "Filières", "Filiere", "Domaine") or ["Autre"])

            coords_second = parse_gps(get_text(actor, "GPS_second"))
            if not coords_second:
                coords_second = coords

            label_pos_s, arrow_style_s = get_style_ancrage(actor, couleur_actor)
            sub_marker_html = f"""
            <div class="marker-wrapper marker-wrapper-sub sub-{hub_class}" data-actor-id="{idx}" data-taille="{taille_actor}" data-trl="{trl_actor_attr}" data-filiere="{filiere_actor}" data-lat="{coords_second[0]}" data-lng="{coords_second[1]}" onclick="openSidebarSingle({idx})" title="{nom_actor_detail}" style="display:none; position:relative; cursor:pointer; z-index:10000;">
                <div style="position:absolute; top:0; left:0; width:12px; height:12px; background:{couleur_actor}; border:2px solid white; border-radius:50%; transform:translate(-50%, -50%); z-index:2;"></div>
                <div style="position:absolute; {label_pos_s} display:flex; align-items:center; z-index:1;">
                    <div style="background:{couleur_actor}; color:white; padding:5px 9px; border-radius:6px; font-size:11px; font-weight:bold; text-align:center; box-shadow:0 2px 6px rgba(0,0,0,0.35); max-width:160px; border:1px solid white;">{nom_actor_court}</div>
                    <div style="width:0; height:0; {arrow_style_s}"></div>
                </div>
            </div>
            """
            folium.Marker(location=coords_second, icon=folium.DivIcon(html=sub_marker_html, icon_size=(0, 0))).add_to(m)

# ==================================
# 6. AFFICHAGE / EXPORT
# ==================================
nom_fichier = f"carte_{MODE}.html"
m.save(nom_fichier)
print(f"✅ Carte exportée : {nom_fichier} (mode = '{MODE}')")

# Sauvegarde aussi sous index.html pour la racine GitHub Pages
m.save("index.html")
print("✅ Carte exportée : index.html (pour la racine GitHub Pages)")

