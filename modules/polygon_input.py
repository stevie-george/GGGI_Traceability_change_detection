import streamlit as st
import geopandas as gpd
import json
from shapely.geometry import shape, Polygon
from streamlit_folium import st_folium
import folium

def get_polygon_from_draw(center=[-23.5, -46.6], zoom=5):
    m = folium.Map(location=center, zoom_start=zoom)
    draw = folium.plugins.Draw(
        export=True,
        draw_options={"polygon": True, "rectangle": True, "circle": False,
                      "marker": False, "polyline": False, "circlemarker": False}
    )
    draw.add_to(m)
    output = st_folium(m, width=700, height=500)
    polygon = None
    if output and output.get("last_active_drawing"):
        geojson = output["last_active_drawing"]
        polygon = shape(geojson["geometry"])
    return polygon

def get_polygon_from_file(uploaded_file):
    import tempfile, os
    suffix = "." + uploaded_file.name.split(".")[-1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(uploaded_file.read())
        tmp_path = f.name
    try:
        if suffix == ".kml":
            import fiona
            fiona.drvsupport.supported_drivers["KML"] = "rw"
            gdf = gpd.read_file(tmp_path, driver="KML")
        else:
            gdf = gpd.read_file(tmp_path)
        gdf = gdf.to_crs("EPSG:4326")
        polygon = gdf.geometry.unary_union
        return polygon
    finally:
        os.unlink(tmp_path)

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