// Line weights: ANC boundaries are thin, ward boundaries thick, and districts get no line (their
// fill is the boundary). The basemap's ANC line layer ships at width 3, so it's overridden here.
// Shared by the ANC, Ward, and District detail pages: draws a whole-boundary outline on top of
// the SMD-colored basemap (skipped when drawOutline is false -- the District page passes this,
// since the single SMD's own fill already reads as its boundary and a second black outline on
// top of it is redundant), framed to fit it. When smdFilter is given (as {year,
// districtDesignators, ancDesignators}), the basemap's SMD fill, SMD label, and ANC boundary-line
// layers are restricted to just those districts/ANCs -- used on all three detail pages so only
// the page's own territory is drawn, with plain basemap showing outside it.
var ANC_LINE_WIDTH = 1;
var WARD_LINE_WIDTH = 3;

function initBoundaryMap(containerId, geometryElementId, accessToken, style, smdFilter, drawOutline, outlineWidth) {
    var geometryTag = document.getElementById(geometryElementId);
    if (!geometryTag) return;
    var geometry = JSON.parse(geometryTag.textContent);
    if (!geometry) return;

    var bounds = new mapboxgl.LngLatBounds();
    (function extend(coords) {
        if (typeof coords[0] === 'number') {
            bounds.extend(coords);
        } else {
            coords.forEach(extend);
        }
    })(geometry.coordinates);

    mapboxgl.accessToken = accessToken;

    function createMap(styleArg) {
        // Passing bounds directly to the constructor (rather than fitBounds() after the fact)
        // means the map renders already framed on the first paint, instead of visibly jumping
        // from the style's default view once it loads.
        var map = new mapboxgl.Map({
            container: containerId,
            style: styleArg,
            bounds: bounds,
            fitBoundsOptions: { padding: 24 },
        });
        map.addControl(new mapboxgl.NavigationControl());

        // The constructor's framing is computed from the container size at that instant. On
        // phones the container's size can change afterward (Safari's toolbars collapsing, rotation,
        // the svh-based height settling), and Mapbox keeps the zoom on resize, leaving the
        // boundary cropped -- so re-fit whenever the container is resized.
        var refit = function () {
            map.fitBounds(bounds, { padding: 24, animate: false });
        };
        map.on('load', refit);
        map.on('resize', refit);

        if (drawOutline === false) return;

        map.on('load', function () {
            map.addSource('boundary', {
                type: 'geojson',
                data: { type: 'Feature', geometry: geometry, properties: {} },
            });
            map.addLayer({
                id: 'boundary-outline',
                type: 'line',
                source: 'boundary',
                paint: { 'line-color': '#222', 'line-width': outlineWidth || WARD_LINE_WIDTH },
            });
        });
    }

    if (!smdFilter) {
        createMap(style);
        return;
    }

    // smd_id looks like "smd_2022_1A02", but for the dozen districts that span two wards (e.g.
    // "6/8F01") it's missing the ward prefix -- smd_name always has the full designator, so
    // filter on that instead and match the year via smd_id.
    var smdMatch = [
        'all',
        ['in', String(smdFilter.year), ['get', 'smd_id']],
        ['in', ['get', 'smd_name'], ['literal', smdFilter.districtDesignators]],
    ];
    var ancMatch = ['in', ['get', 'NAME'], ['literal', smdFilter.ancDesignators]];

    // These are the SMD-fill, SMD-label, and ANC-boundary-line layer ids baked into the current
    // Mapbox Studio style (MAPBOX_SMD_STYLE) -- found by inspecting that style's layer list.
    var layerFilters = {
        'smd': smdMatch,
        'to-mapbox-label-points-2022-d-9kxn2y': smdMatch,
        'anc-2022-6ps93f': ancMatch,
    };

    // The filter is baked into the style JSON itself, before the map is constructed, so the
    // filtered view is what renders on the very first frame -- setFilter()'ing after the fact
    // would draw the full citywide basemap for a moment and then visibly cut it down.
    var styleUrlMatch = /^mapbox:\/\/styles\/(.+)$/.exec(style);
    var styleRequestUrl = 'https://api.mapbox.com/styles/v1/' + styleUrlMatch[1]
        + '?access_token=' + encodeURIComponent(accessToken);

    fetch(styleRequestUrl)
        .then(function (resp) { return resp.json(); })
        .then(function (styleJson) {
            styleJson.layers.forEach(function (layer) {
                if (layerFilters[layer.id]) {
                    layer.filter = layerFilters[layer.id];
                }
                if (layer.id === 'anc-2022-6ps93f') {
                    layer.paint['line-width'] = ANC_LINE_WIDTH;
                }
            });
            createMap(styleJson);
        });
}
