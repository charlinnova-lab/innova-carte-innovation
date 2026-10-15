/* =========================================================
   CARTOGRAPHIE FILIERE - LOGIQUE INTERACTIVE
   ========================================================= */

var mapObject = null;

document.addEventListener("DOMContentLoaded", function() {
    for (var key in window) {
        if (key.startsWith("map_") && window[key] instanceof L.Map) {
            mapObject = window[key];
            break;
        }
    }
    
    var sidebar = document.getElementById('sidebar');
    if (sidebar && typeof L !== 'undefined') {
        L.DomEvent.disableScrollPropagation(sidebar);
        L.DomEvent.disableClickPropagation(sidebar);
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
    document.querySelectorAll('#panel-search, #panel-filter').forEach(function(p) {
        p.style.display = 'none';
    });
    panel.style.display = isOpen ? 'none' : 'block';
}

function toggleAllFilters(className, masterCheckbox) {
    var checkboxes = document.querySelectorAll('.' + className);
    checkboxes.forEach(function(cb) {
        cb.checked = masterCheckbox.checked;
    });
    applyFilters();
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

                var shouldShow = (!hostVisible || searchQuery) && subMatchTaille && subMatchTrl && subMatchSearch && subMatchFiliere;
                subEl.style.display = shouldShow ? 'flex' : 'none';
            });
        }
    });

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
    var sidebarWidth = (sidebarEl && window.innerWidth > 768) ? sidebarEl.offsetWidth : 0;

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
        
        if (typeof gtag === 'function') {
            var titleElem = contentNode.querySelector('h1');
            var actorName = titleElem ? titleElem.innerText : ('ID ' + id);
            gtag('event', 'consultation_fiche', {
                'event_category': 'Acteur',
                'event_label': actorName
            });
        }

        contentNode.querySelectorAll('a').forEach(function(link) {
            link.setAttribute('target', '_blank');
            link.setAttribute('rel', 'noopener noreferrer');
        });

        wrapper.appendChild(contentNode);
        container.appendChild(wrapper);
    }
    var sidebar = document.getElementById('sidebar');
    sidebar.scrollTop = 0;
    sidebar.classList.add('open');
    sidebar.style.right = '0px';
}

function closeSidebar() {
    var sidebar = document.getElementById('sidebar');
    sidebar.classList.remove('open');
    sidebar.style.right = '-100%';
}
