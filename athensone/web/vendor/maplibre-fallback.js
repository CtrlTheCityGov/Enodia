// Offline fallback for MapLibre GL JS 5.3.0: if the jsDelivr copy did not load (venue Wi-Fi, blocked CDN),
// load the identical vendored build. Must be a classic, synchronous script placed right after the CDN tag.
if (!window.maplibregl) {
  document.write('<link rel="stylesheet" href="/web/vendor/maplibre-gl-5.3.0/maplibre-gl.css">' +
    '<script src="/web/vendor/maplibre-gl-5.3.0/maplibre-gl.js"><\/script>');
}
