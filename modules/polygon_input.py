import streamlit as st
import geopandas as gpd
import json
from shapely.geometry import shape, Polygon
from streamlit_folium import st_folium
import folium

def get_polygon_from_draw(center=[20.0, -102.0], zoom=6):
    import folium.plugins as plugins
    import streamlit.components.v1 as components

    m = folium.Map(
        location=center,
        zoom_start=zoom,
        tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        attr="Google Satellite",
        max_zoom=21,
        prefer_canvas=True
    )

    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
        attr="Google Hybrid", name="Google Hybrid",
        overlay=False, control=True, max_zoom=21
    ).add_to(m)

    folium.TileLayer(
        tiles="OpenStreetMap", name="OpenStreetMap",
        overlay=False, control=True
    ).add_to(m)

    plugins.Draw(
        export=True,
        draw_options={
            "polygon": True, "rectangle": True,
            "circle": False, "marker": False,
            "polyline": False, "circlemarker": False
        },
        edit_options={"edit": True, "remove": True}
    ).add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    # Renderiza el mapa como HTML a pantalla completa
    map_html = m._repr_html_()
    full_html = f"""
        <html><body style="margin:0;padding:0;">
        <div id="map" style="width:100%;height:80vh;">{map_html}</div>
        <div id="coords" style="display:none;"></div>
        <script>
            // Captura el último polígono dibujado y lo manda a Streamlit
            document.addEventListener('DOMContentLoaded', function() {{
                var mapEl = document.querySelector('.folium-map');
                if (mapEl && mapEl._leaflet_map) {{
                    mapEl._leaflet_map.on('draw:created', function(e) {{
                        var geo = e.layer.toGeoJSON();
                        window.parent.postMessage({{type:'polygon', data: JSON.stringify(geo)}}, '*');
                    }});
                }}
            }});
        </script>
        </body></html>
    """
    components.html(full_html, height=int(650), scrolling=False)

    # Para este método usamos st_folium para capturar el polígono
    output = st_folium(m, width=0, height=0, returned_objects=["last_active_drawing"], key="hidden_map")
    polygon = None
    if output and output.get("last_active_drawing"):
        geojson = output["last_active_drawing"]
        polygon = shape(geojson["geometry"])
    return polygon



def get_polygon_from_file(uploaded_file):
    import tempfile, os, zipfile
    suffix = "." + uploaded_file.name.split(".")[-1].lower()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = os.path.join(tmpdir, uploaded_file.name)
        with open(tmp_path, "wb") as f:
            f.write(uploaded_file.read())
        
        try:
            # Si es zip, extrae primero
            if suffix == ".zip":
                with zipfile.ZipFile(tmp_path, "r") as z:
                    z.extractall(tmpdir)
                # Busca el .shp dentro del zip
                shp_files = [f for f in os.listdir(tmpdir) if f.endswith(".shp")]
                if shp_files:
                    tmp_path = os.path.join(tmpdir, shp_files[0])
                else:
                    # Puede ser un geojson dentro del zip
                    geojson_files = [f for f in os.listdir(tmpdir) if f.endswith(".geojson")]
                    if geojson_files:
                        tmp_path = os.path.join(tmpdir, geojson_files[0])

            if suffix == ".kml":
                import fiona
                fiona.drvsupport.supported_drivers["KML"] = "rw"
                gdf = gpd.read_file(tmp_path, driver="KML")
            else:
                gdf = gpd.read_file(tmp_path)

            gdf = gdf.to_crs("EPSG:4326")
            polygon = gdf.geometry.unary_union
            return polygon

        except Exception as e:
            st.error(f"Error leyendo archivo: {e}")
            return None

def get_polygon_from_coords(coords_text):
    try:
        pairs = [line.strip().split(",") for line in coords_text.strip().split("\n") if line.strip()]
        coords = [(float(p[1]), float(p[0])) for p in pairs]
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        return Polygon(coords)
    except Exception as e:
        st.error(f"Error al leer coordenadas: {e}")
        return None