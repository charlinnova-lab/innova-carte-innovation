// =========================================================
// CARTOGRAPHIE FILIERE - LOGIQUE JAVASCRIPT
// (c) Charlotte Piau - innov'a
// Last Modification : 15/10 - Filtres unifiés (marqueurs simples, hubs,
//                     sous-fiches, recherche) + diagnostic console
// =========================================================

var mapObject = null;
var selectedFiliere = 'all';
var _ficheTextCache = {};

document.addEventListener("DOMContentLoaded", function() {
    for (var key in window) {
        try {
            if (window[key] instanceof L.Map) {
                mapObject = window[key];
                break;
            }
        } catch (e) { /* propriété inaccessible : on ignore */ }
    }
    diagnosticFiltres();
});

// ==================================
// OUTILS DE NORMALISATION
// ==================================

// Compare sans tenir compte de la casse, des accents, des apostrophes
// typographiques, des sauts de ligne et des espaces multiples.
function norm(val) {
    if (val === null || val === undefined) return '';
    return String(val)
        .replace(/[\u2018\u2019]/g, "'")
        .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
        .replace(/\s+/g, ' ')
        .trim()
        .toLowerCase();
}

function cleanTaille(val) {
    return norm(val);
}

function splitAttr(el, attrName) {
    return (el.getAttribute(attrName) || '')
        .split('|||')
        .map(norm)
        .filter(function(s) { return s !== ''; });
}

function getFicheText(actorId) {
    if (_ficheTextCache[actorId] === undefined) {
        var fiche = document.getElementById('fiche-acteur-' + actorId);
        _ficheTextCache[actorId] = fiche ? norm(fiche.textContent) : '';
    }
    return _ficheTextCache[actorId];
}

function getHubClass(el) {
    return Array.from(el.classList).find(function(c) {
        return c.indexOf('hub-marker-') === 0;
    });
}

// ==================================
// PANNEAUX
// ==================================

function togglePanel(panelId, btnId) {
    var panel = document.getElementById(panelId);
    var btn = document.getElementById(btnId);
    if (!panel) return;

    var isVisible = panel.style.display === 'block';

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
    document.querySelectorAll('.' + className).forEach(function(cb) {
        cb.checked = masterCheckbox.checked;
    });
    applyFilters();
}

// Garde la case « Tout cocher / décocher » cohérente avec les cases individuelles
function syncMaster(className, masterId) {
    var boxes = document.querySelectorAll('.' + className);
    var master = document.getElementById(masterId);
    if (!master || boxes.length === 0) return;
    var nbChecked = document.querySelectorAll('.' + className + ':checked').length;
    master.checked = (nbChecked === boxes.length);
    master.indeterminate = (nbChecked > 0 && nbChecked < boxes.length);
}

// ==================================
// FILTRES : UN SEUL CERVEAU POUR TOUT
// ==================================

function filterFiliere(filiereVal, btnElement) {
    selectedFiliere = filiereVal;

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

// Lit l'état courant de tous les filtres
function getCriteria() {
    var searchInput = document.getElementById('global-search-input');
    return {
        hasTailleFilter: document.querySelectorAll('.filter-taille').length > 0,
        tailles: Array.from(document.querySelectorAll('.filter-taille:checked'))
            .map(function(cb) { return norm(cb.value); }),
        hasTrlFilter: document.querySelectorAll('.filter-trl').length > 0,
        trls: Array.from(document.querySelectorAll('.filter-trl:checked'))
            .map(function(cb) { return norm(cb.value); }),
        filiere: selectedFiliere,
        query: searchInput ? norm(searchInput.value) : ''
    };
}

// Une fiche (marqueur simple, hôte ou sous-fiche) passe-t-elle tous les filtres ?
function matchesCriteria(el, c) {
    // 1. Type de structure (chaque fiche a sa propre typologie)
    if (c.hasTailleFilter) {
        var taille = norm(el.getAttribute('data-taille')) || 'autre';
        if (c.tailles.indexOf(taille) === -1) return false;
    }

    // 2. TRL : une fiche sans TRL n'est pas exclue, sauf si tout est décoché
    if (c.hasTrlFilter) {
        if (c.trls.length === 0) return false;
        var elTrls = splitAttr(el, 'data-trl');
        if (elTrls.length > 0) {
            var trlOk = elTrls.some(function(t) { return c.trls.indexOf(t) !== -1; });
            if (!trlOk) return false;
        }
    }

    // 3. Filière
    if (c.filiere !== 'all') {
        if (splitAttr(el, 'data-filiere').indexOf(norm(c.filiere)) === -1) return false;
    }

    // 4. Recherche plein texte dans la fiche
    if (c.query) {
        if (getFicheText(el.getAttribute('data-actor-id')).indexOf(c.query) === -1) return false;
    }

    return true;
}

function applyFilters() {
    var c = getCriteria();

    syncMaster('filter-taille', 'master-taille');
    syncMaster('filter-trl', 'master-trl');

    // 1. Marqueurs simples et hôtes de hub
    document.querySelectorAll('.marker-wrapper-host').forEach(function(host) {
        var hubClass = getHubClass(host);
        var nbSubMatch = 0;

        if (hubClass) {
            document.querySelectorAll('.sub-' + hubClass).forEach(function(sub) {
                if (matchesCriteria(sub, c)) nbSubMatch++;
            });
        }

        // Le compteur « +N » reflète les sous-fiches qui passent les filtres
        var badge = host.querySelector('.hub-count');
        if (badge) {
            badge.textContent = '+' + nbSubMatch;
            if (badge.parentNode) {
                badge.parentNode.style.display = nbSubMatch > 0 ? 'block' : 'none';
            }
        }

        // Le hub reste visible si lui-même OU l'une de ses sous-fiches correspond
        var shouldShow = matchesCriteria(host, c) || nbSubMatch > 0;

        if (host.getAttribute('data-hub-opened') === 'true') {
            host.style.display = 'none';
        } else {
            host.style.display = shouldShow ? 'flex' : 'none';
        }
    });

    // 2. Sous-fiches des hubs ouverts
    document.querySelectorAll('.marker-wrapper-sub').forEach(function(sub) {
        if (sub.getAttribute('data-active-hub') !== 'true') return;
        sub.style.display = matchesCriteria(sub, c) ? 'flex' : 'none';
    });
}

// Aide au débogage : signale dans la console (F12) les valeurs de "Taille"
// qui ne correspondent à aucune case du filtre.
function diagnosticFiltres() {
    var connus = Array.from(document.querySelectorAll('.filter-taille'))
        .map(function(cb) { return norm(cb.value); });
    var inconnus = {};

    document.querySelectorAll('[data-taille]').forEach(function(el) {
        var t = norm(el.getAttribute('data-taille')) || 'autre';
        if (connus.indexOf(t) === -1) inconnus[t] = (inconnus[t] || 0) + 1;
    });

    if (Object.keys(inconnus).length > 0) {
        console.warn('[Filtres] Types de structure sans case correspondante (ces fiches disparaissent dès qu\'un filtre est appliqué) :', inconnus);
    }
    if (document.querySelectorAll('.filter-trl').length === 0) {
        console.warn('[Filtres] Aucune case TRL générée : le filtre TRL est ignoré.');
    }
}

// ==================================
// HUBS (GRAPPES)
// ==================================

function handleHubClick(lat, lng, hubClass, hoteId) {
    if (!mapObject) return;

    // 1. Referme tout hub déjà ouvert
    document.querySelectorAll('.marker-wrapper-host').forEach(function(host) {
        host.removeAttribute('data-hub-opened');
    });
    document.querySelectorAll('.marker-wrapper-sub').forEach(function(sub) {
        sub.style.display = 'none';
        sub.removeAttribute('data-active-hub');
    });

    // 2. Ouvre le hub cliqué
    var mainMarker = document.querySelector('.' + hubClass);
    if (mainMarker) mainMarker.setAttribute('data-hub-opened', 'true');
    document.querySelectorAll('.sub-' + hubClass).forEach(function(sub) {
        sub.setAttribute('data-active-hub', 'true');
    });

    // 3. Les filtres décident de ce qui est affiché (hôtes comme sous-fiches)
    applyFilters();
    fitGroupToVisible(hubClass, lat, lng);

    if (hoteId !== undefined && hoteId !== null) {
        openSidebarSingle(hoteId);
    }

    var btnDezoom = document.getElementById('btn-dezoom');
    if (btnDezoom) btnDezoom.style.display = 'block';
}

// Cadre la carte sur l'hôte et sur les sous-fiches qui passent les filtres
function fitGroupToVisible(hubClass, hostLat, hostLng) {
    if (!mapObject) return;

    var c = getCriteria();
    var bounds = L.latLngBounds([[hostLat, hostLng]]);

    document.querySelectorAll('.sub-' + hubClass).forEach(function(sub) {
        if (!matchesCriteria(sub, c)) return;
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

    document.querySelectorAll('.marker-wrapper-host').forEach(function(host) {
        host.removeAttribute('data-hub-opened');
    });
    document.querySelectorAll('.marker-wrapper-sub').forEach(function(sub) {
        sub.style.display = 'none';
        sub.removeAttribute('data-active-hub');
    });

    // Réaffiche les hôtes en respectant les filtres en cours
    applyFilters();

    var btnDezoom = document.getElementById('btn-dezoom');
    if (btnDezoom) btnDezoom.style.display = 'none';

    var zoom = (typeof initialZoom !== 'undefined') ? initialZoom : 13;
    mapObject.setView([49.89, 2.30], zoom, { animate: true });
    closeSidebar();
}

// ==================================
// FICHE LATÉRALE ET INFOBULLES
// ==================================

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

    document.querySelectorAll('.tooltip-text').forEach(function(tip) {
        if (tip !== tooltip) tip.style.display = 'none';
    });

    tooltip.style.display = (tooltip.style.display === 'block') ? 'none' : 'block';
}

document.addEventListener('click', function(e) {
    if (!e.target.closest('.tooltip-container')) {
        document.querySelectorAll('.tooltip-text').forEach(function(tip) {
            tip.style.display = 'none';
        });
    }
});
