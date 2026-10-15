// =========================================================
// CARTOGRAPHIE FILIERE - LOGIQUE JAVASCRIPT
// ==================================

var mapObject = null;
var selectedFiliere = 'all';

// Initialisation de la carte et des écouteurs globaux
document.addEventListener("DOMContentLoaded", function() {
    // Recherche de l'instance Leaflet globale si elle existe
    for (var key in window) {
        if (window[key] instanceof L.Map) {
            mapObject = window[key];
            break;
        }
    }
});

function togglePanel(panelId, btnId) {
    var panel = document.getElementById(panelId);
    var btn = document.getElementById(btnId);
    if (!panel) return;

    var isVisible = panel.style.display === 'block';
    
    // Fermer les autres panneaux
    ['panel-search', 'panel-filter'].forEach(function(pId) {
        var p = document.getElementById(pId);
        if (p) p.style.display = 'none';
    });
    ['icon-search-btn', 'icon-filter-btn'].forEach(function(bId) {
        var b = document.getElementById(bId);
        if (b) b.style.background = 'white';
    });

    if (!isVisible) {
        panel.style.display = 'block';
        if (btn) btn.style.background = '#EAEAEA';
    }
}

function toggleAccordion(contentId) {
    var content = document.getElementById(contentId);
    var arrow = document.getElementById(contentId + '-arrow');
    if (!content) return;

    if (content.style.display === 'block') {
        content.style.display = 'none';
        if (arrow) arrow.style.transform = 'rotate(0deg)';
    } else {
        content.style.display = 'block';
        if (arrow) arrow.style.transform = 'rotate(180deg)';
    }
}

function toggleAllFilters(className, masterCheckbox) {
    var checkboxes = document.querySelectorAll('.' + className);
    checkboxes.forEach(function(cb) {
        cb.checked = masterCheckbox.checked;
    });
    applyFilters();
}

function cleanTaille(val) {
    if (!val) return '';
    return val.trim().replace(/\n/g, ' ').replace(/\r/g, '');
}

function filterFiliere(filiereVal, btnElement) {
    selectedFiliere = filiereVal;
    
    // Gestion visuelle des boutons de filière
    document.querySelectorAll('.filter-btn').forEach(function(btn) {
        btn.style.background = '#EAEAEA';
        btn.style.color = '#333';
        btn.classList.remove('active');
    });
    if (btnElement) {
        btnElement.style.background = '#2D3277';
        btnElement.style.color = 'white';
        btnElement.classList.add('active');
    }

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

    function matchesFiliereByElement(el) {
        if (selectedFiliere === 'all') return true;
        var vals = (el.getAttribute('data-filiere') || '').split('|||').map(function(s) { return s.trim(); });
        return vals.indexOf(selectedFiliere) !== -1;
    }

    // Filtrage des marqueurs simples et hôtes
    document.querySelectorAll('.marker-wrapper-host').forEach(function(el) {
        var rawTaille = cleanTaille(el.getAttribute('data-taille'));
        var elTrlsList = (el.getAttribute('data-trl') || '').toLowerCase()
                         .split('|||').map(function(s) { return s.trim(); });
        var actorId = el.getAttribute('data-actor-id');

        var matchTaille = selectedTailles.indexOf(rawTaille) !== -1;
        var matchTrl = elTrlsList.length === 0 || elTrlsList.some(function(trl) {
            return trl === '' || selectedTrls.indexOf(trl) !== -1;
        });
        var matchSearch = matchesSearch(actorId);
        var matchFiliere = matchesFiliereByElement(el);

        var shouldShow = matchTaille && matchTrl && matchSearch && matchFiliere;
        
        // Si le hub est actuellement ouvert, on cache l'hôte mais on laisse les sous-marqueurs gérer leur affichage
        if (el.getAttribute('data-hub-opened') === 'true') {
            el.style.display = 'none';
        } else {
            el.style.display = shouldShow ? 'flex' : 'none';
        }
    });

    // Filtrage des sous-marqueurs (si un hub est ouvert)
    document.querySelectorAll('.marker-wrapper-sub').forEach(function(el) {
        if (el.getAttribute('data-active-hub') !== 'true') return;

        var rawTaille = cleanTaille(el.getAttribute('data-taille'));
        var elTrlsList = (el.getAttribute('data-trl') || '').toLowerCase()
                         .split('|||').map(function(s) { return s.trim(); });
        var actorId = el.getAttribute('data-actor-id');

        var matchTaille = selectedTailles.indexOf(rawTaille) !== -1;
        var matchTrl = elTrlsList.length === 0 || elTrlsList.some(function(trl) {
            return trl === '' || selectedTrls.indexOf(trl) !== -1;
        });
        var matchSearch = matchesSearch(actorId);
        var matchFiliere = matchesFiliereByElement(el);

        el.style.display = (matchTaille && matchTrl && matchSearch && matchFiliere) ? 'flex' : 'none';
    });
}

function handleHubClick(lat, lng, hubClass, hoteId) {
    if (!mapObject) return;

    // 1. Fermeture propre de tous les autres hubs ouverts pour éviter les superpositions d'étiquettes
    document.querySelectorAll('.marker-wrapper-host').forEach(function(host) {
        if (host.getAttribute('data-hub-opened') === 'true') {
            host.removeAttribute('data-hub-opened');
            host.style.display = 'flex';
        }
    });
    document.querySelectorAll('.marker-wrapper-sub').forEach(function(sub) {
        sub.style.display = 'none';
        sub.removeAttribute('data-active-hub');
    });

    // 2. Zoom et centrage sur le hub sélectionné
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

    // Affichage des sous-marqueurs du hub actif selon les filtres
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

    var btnDezoom = document.getElementById('btn-dezoom');
    if (btnDezoom) btnDezoom.style.display = 'block';
}

function fitGroupToVisible(hubClass, hostLat, hostLng) {
    if (!mapObject) return;
    
    var subMarkers = document.querySelectorAll('.sub-' + hubClass);
    var bounds = L.latLngBounds([[hostLat, hostLng]]);
    
    subMarkers.forEach(function(sub) {
        var lat = parseFloat(sub.getAttribute('data-lat'));
        var lng = parseFloat(sub.getAttribute('data-lng'));
        if (!isNaN(lat) && !isNaN(lng)) {
            bounds.extend([lat, lng]);
        }
    });

    mapObject.fitBounds(bounds, {
        padding: [80, 80],
        maxZoom: 17,
        animate: true
    });
}

function resetZoomHub() {
    if (!mapObject) return;

    // Réinitialisation de tous les hubs ouverts
    document.querySelectorAll('.marker-wrapper-host').forEach(function(host) {
        host.removeAttribute('data-hub-opened');
        host.style.display = 'flex';
    });

    document.querySelectorAll('.marker-wrapper-sub').forEach(function(sub) {
        sub.style.display = 'none';
        sub.removeAttribute('data-active-hub');
    });

    var btnDezoom = document.getElementById('btn-dezoom');
    if (btnDezoom) btnDezoom.style.display = 'none';

    mapObject.setView([49.89, 2.30], initialZoom, { animate: true });
    closeSidebar();
}

function openSidebarSingle(actorId) {
    var fiche = document.getElementById('fiche-acteur-' + actorId);
    var sidebarContainer = document.getElementById('sidebar-container');
    var sidebar = document.getElementById('sidebar');

    if (fiche && sidebarContainer && sidebar) {
        sidebarContainer.innerHTML = fiche.innerHTML;
        sidebar.style.right = '0';
    }
}

function closeSidebar() {
    var sidebar = document.getElementById('sidebar');
    if (sidebar) {
        sidebar.style.right = '-720px';
    }
}

function togglePopupInfo(event, btnElement) {
    event.stopPropagation();
    var container = btnElement.closest('.tooltip-container');
    if (!container) return;
    
    var tooltip = container.querySelector('.tooltip-text');
    if (!tooltip) return;

    // Fermer les autres infobulles ouvertes
    document.querySelectorAll('.tooltip-text').forEach(function(tip) {
        if (tip !== tooltip) tip.style.display = 'none';
    });

    tooltip.style.display = (tooltip.style.display === 'block') ? 'none' : 'block';
}

// Fermeture des infobulles au clic en dehors
document.addEventListener('click', function(e) {
    if (!e.target.closest('.tooltip-container')) {
        document.querySelectorAll('.tooltip-text').forEach(function(tip) {
            tip.style.display = 'none';
        });
    }
});
