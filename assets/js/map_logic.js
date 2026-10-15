// =========================================================
// CARTOGRAPHIE FILIERE - LOGIQUE JAVASCRIPT
// (c) Charlotte Piau - innov'a
// Last Modification : Les filtres multiples
// ==================================

var mapObject = null;
var selectedFiliere = 'all';

document.addEventListener("DOMContentLoaded", function() {
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

    // Correspondance TRL souple (gère les phrases complètes d'Airtable)
    function matchesTrl(elTrlAttr) {
        if (selectedTrls.length === 0) return false;
        var elTrlsList = (elTrlAttr || '').toLowerCase().split('|||').map(function(s) { return s.trim(); });
        if (elTrlsList.length === 0 || elTrlsList.includes('')) return true;
        
        return elTrlsList.some(function(trlItem) {
            return selectedTrls.some(function(selTrl) {
                return trlItem.indexOf(selTrl) !== -1 || selTrl.indexOf(trlItem) !== -1;
            });
        });
    }

    function elementMatchesCriteria(el) {
        var rawTaille = cleanTaille(el.getAttribute('data-taille'));
        var actorId = el.getAttribute('data-actor-id');

        var matchTaille = selectedTailles.indexOf(rawTaille) !== -1;
        var matchTrlVal = matchesTrl(el.getAttribute('data-trl'));
        var matchSearch = matchesSearch(actorId);
        var matchFiliere = matchesFiliereByElement(el);

        return matchTaille && matchTrlVal && matchSearch && matchFiliere;
    }

    // 1. Filtrage des marqueurs simples et hôtes
    document.querySelectorAll('.marker-wrapper-host').forEach(function(el) {
        var selfMatch = elementMatchesCriteria(el);
        var groupClass = Array.from(el.classList).find(function(c) { return c.startsWith('hub-marker-'); });
        
        var subMatch = false;
        if (groupClass) {
            var subElements = document.querySelectorAll('.sub-' + groupClass);
            subElements.forEach(function(sub) {
                if (elementMatchesCriteria(sub)) {
                    subMatch = true;
                }
            });
        }

        // L'hôte reste visible s'il correspond lui-même ou si l'un de ses enfants/labos correspond
        var shouldShow = selfMatch || subMatch;
        
        if (el.getAttribute('data-hub-opened') === 'true') {
            el.style.display = 'none';
        } else {
            el.style.display = shouldShow ? 'flex' : 'none';
        }
    });

    // 2. Filtrage des sous-marqueurs (les labos dans les hubs ouverts)
    document.querySelectorAll('.marker-wrapper-sub').forEach(function(el) {
        if (el.getAttribute('data-active-hub') !== 'true') return;
        el.style.display = elementMatchesCriteria(el) ? 'flex' : 'none';
    });
}

function handleHubClick(lat, lng, hubClass, hoteId) {
    if (!mapObject) return;

    // Fermeture propre des autres hubs ouverts
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

    function matchesTrlSub(elTrlAttr) {
        if (selectedTrls.length === 0) return false;
        var elTrlsList = (elTrlAttr || '').toLowerCase().split('|||').map(function(s) { return s.trim(); });
        if (elTrlsList.length === 0 || elTrlsList.includes('')) return true;
        
        return elTrlsList.some(function(trlItem) {
            return selectedTrls.some(function(selTrl) {
                return trlItem.indexOf(selTrl) !== -1 || selTrl.indexOf(trlItem) !== -1;
            });
        });
    }

    document.querySelectorAll('.sub-' + hubClass).forEach(function(el) {
        el.setAttribute('data-active-hub', 'true');

        var rawTaille = cleanTaille(el.getAttribute('data-taille'));
        var actorId = el.getAttribute('data-actor-id');

        var matchTaille = selectedTailles.indexOf(rawTaille) !== -1;
        var matchTrlVal = matchesTrlSub(el.getAttribute('data-trl'));
        var matchSearch = matchesSearch(actorId);
        var matchFiliere = matchesFiliere(el);

        el.style.display = (matchTaille && matchTrlVal && matchSearch && matchFiliere) ? 'flex'
