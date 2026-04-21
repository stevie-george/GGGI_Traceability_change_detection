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