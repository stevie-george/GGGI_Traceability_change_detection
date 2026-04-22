import folium
import json
from shapely.geometry import mapping

LAYER_STYLES = {
    "hansen":    {"color": "#e74c3c", "name": "Hansen - Pérdida forestal"},
    "glad":      {"color": "#e67e22", "name": "GLAD - Alertas"},
    "jrc_defor": {"color": "#8e44ad", "name": "JRC - Deforestación"},
    "jrc_degrad":{"color": "#d35400", "name": "JRC - Degradación"},
    "firms":     {"color": "#f39c12", "name": "FIRMS - Incendios activos"},
    "modis":     {"color": "#c0392b", "name": "MODIS - Área quemada"},
    "amazon":    {"color": "#16a085", "name": "JRC Amazon - Regrowth"},
}

def add_tile_layer(m, tile_url, name, color):
    if tile_url:
        folium.TileLayer(
            tiles=tile_url,
            attr=name,
            name=f'<span style="color:{color}">■</span> {name}',
            overlay=True,
            control=True,
            opacity=0.7
        ).add_to(m)

def create_alert_map(polygon, results=None, center=None):
    if center is None:
        centroid = polygon.centroid
        center = [centroid.y, centroid.x]

    m = folium.Map(location=center, zoom_start=12, tiles="CartoDB positron")

    # Polígono principal
    folium.GeoJson(
        data=json.dumps({"type": "Feature", "geometry": mapping(polygon)}),
        style_function=lambda x: {
            "fillColor": "#2ecc71", "color": "#27ae60",
            "weight": 3, "fillOpacity": 0.1
        },
        name="Polígono analizado",
        tooltip="Área de análisis"
    ).add_to(m)

    if results:
        # Hansen - pérdida por año con escala de color
        hansen = results.get("hansen", {})
        if hansen.get("loss_image"):
            tile_url = get_tile_url(
                hansen["loss_image"],
                {"min": 1, "max": 23,
                 "palette": ["ffffcc", "fed976", "fd8d3c", "e31a1c", "800026"]}
            )
            add_tile_layer(m, tile_url, LAYER_STYLES["hansen"]["name"],
                           LAYER_STYLES["hansen"]["color"])

        # GLAD alerts
        glad = results.get("glad", {})
        if glad.get("alert_image"):
            tile_url = get_tile_url(
                glad["alert_image"],
                {"min": 1, "max": 365, "palette": ["ff6600", "ff0000"]}
            )
            add_tile_layer(m, tile_url, LAYER_STYLES["glad"]["name"],
                           LAYER_STYLES["glad"]["color"])

        # JRC deforestación
        jrc = results.get("jrc", {})
        if jrc.get("defor_image"):
            tile_url = get_tile_url(
                jrc["defor_image"],
                {"min": 1, "max": 1, "palette": ["8e44ad"]}
            )
            add_tile_layer(m, tile_url, LAYER_STYLES["jrc_defor"]["name"],
                           LAYER_STYLES["jrc_defor"]["color"])

        # JRC degradación
        if jrc.get("degrad_image"):
            tile_url = get_tile_url(
                jrc["degrad_image"],
                {"min": 1, "max": 1, "palette": ["d35400"]}
            )
            add_tile_layer(m, tile_url, LAYER_STYLES["jrc_degrad"]["name"],
                           LAYER_STYLES["jrc_degrad"]["color"])

        # FIRMS incendios
        firms = results.get("firms", {})
        if firms.get("fire_image"):
            tile_url = get_tile_url(
                firms["fire_image"],
                {"min": 300, "max": 400, "palette": ["ffff00", "ff6600", "ff0000"]}
            )
            add_tile_layer(m, tile_url, LAYER_STYLES["firms"]["name"],
                           LAYER_STYLES["firms"]["color"])

        # MODIS burn area
        modis = results.get("modis", {})
        if modis.get("burn_image"):
            tile_url = get_tile_url(
                modis["burn_image"],
                {"min": 1, "max": 366, "palette": ["ffd700", "ff4500", "8b0000"]}
            )
            add_tile_layer(m, tile_url, LAYER_STYLES["modis"]["name"],
                           LAYER_STYLES["modis"]["color"])

    legend_html = """
    <div style="position: fixed; bottom: 30px; left: 30px; z-index: 1000;
         background: rgba(15, 15, 15, 0.85);
         padding: 14px 18px; border-radius: 10px;
         border: 1px solid rgba(255,255,255,0.15);
         font-size: 13px; line-height: 2;
         font-family: Arial, sans-serif;
         box-shadow: 0 4px 12px rgba(0,0,0,0.4);">
        <div style="color: #ffffff; font-weight: bold; font-size: 14px;
                    margin-bottom: 6px; border-bottom: 1px solid rgba(255,255,255,0.2);
                    padding-bottom: 4px;">
            🗺️ Leyenda
        </div>
        <div style="color: #ffffff;">
            <span style="color:#2ecc71; font-size:16px;">■</span>&nbsp; Polígono analizado<br>
            <span style="color:#ff4d4d; font-size:16px;">■</span>&nbsp; Hansen — pérdida forestal<br>
            <span style="color:#ff9933; font-size:16px;">■</span>&nbsp; GLAD — alertas<br>
            <span style="color:#cc66ff; font-size:16px;">■</span>&nbsp; JRC — deforestación<br>
            <span style="color:#ff6600; font-size:16px;">■</span>&nbsp; JRC — degradación<br>
            <span style="color:#ffcc00; font-size:16px;">■</span>&nbsp; FIRMS — incendios<br>
            <span style="color:#ff3333; font-size:16px;">■</span>&nbsp; MODIS — área quemada<br>
        </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    folium.LayerControl(collapsed=False).add_to(m)
    folium.plugins.Fullscreen().add_to(m)
    folium.plugins.MeasureControl().add_to(m)

    return m

def get_tile_url(image, vis_params):
    try:
        map_id = image.getMapId(vis_params)
        return map_id['tile_fetcher'].url_format
    except:
        return None