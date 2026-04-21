import streamlit as st
from streamlit_folium import st_folium

from modules.polygon_input import get_polygon_from_draw, get_polygon_from_file, get_polygon_from_coords
from modules.gee_analysis import (initialize_gee, analyze_hansen, analyze_glad,
                                   analyze_jrc_deforestation, analyze_firms,
                                   analyze_modis_burn, analyze_jrc_amazon,
                                   get_polygon_area_ha)
from modules.map_viewer import create_alert_map
from modules.report_generator import generate_pdf, generate_excel


# DEBUG - borrar después
try:
    import ee, json
    creds_json = st.secrets["earthengine"]["credentials"]
    service_account = st.secrets["earthengine"]["service_account"]
    
    # Muestra info de las credenciales
    creds_dict = json.loads(creds_json)
    st.write(f"Type: {creds_dict.get('type')}")
    st.write(f"Project: {creds_dict.get('project_id')}")
    st.write(f"Client email: {creds_dict.get('client_email')}")
    
    # Intenta inicializar
    credentials = ee.ServiceAccountCredentials(service_account, key_data=creds_json)
    ee.Initialize(credentials=credentials, project="ee-stephaniegeorge")
    st.success("GEE OK!")
    
except Exception as e:
    st.error(f"Error exacto: {str(e)}")

###
st.set_page_config(page_title="Alertas Deforestación MX", page_icon="🌿", layout="wide")

st.title("🌿 Sistema de Alertas — Cero Deforestación")
st.markdown("Monitoreo para cultivos de **aguacate** y **agave tequilana** en México")

with st.sidebar:
    st.header("⚙️ Configuración")
    cultivo = st.selectbox("Cultivo", ["Aguacate", "Agave tequilana", "Otro"])
    start_year = st.slider("Año inicio", 2001, 2023, 2015)
    end_year   = st.slider("Año fin",    2001, 2023, 2023)

    st.subheader("Fuentes de datos")
    use_hansen = st.checkbox("Hansen (pérdida forestal)", value=True)
    use_glad   = st.checkbox("GLAD (alertas)", value=True)
    use_jrc    = st.checkbox("JRC (deforestación + degradación)", value=True)
    use_firms  = st.checkbox("FIRMS NASA (incendios activos)", value=True)
    use_modis  = st.checkbox("MODIS (área quemada)", value=True)
    use_amazon = st.checkbox("JRC Amazon (regrowth 2023)", value=False)

    st.divider()
    gee_ok = initialize_gee()
    if gee_ok:
        st.success("GEE conectado ✓")
    else:
        st.error("GEE no conectado")

tab1, tab2, tab3 = st.tabs(["📍 Polígono", "🗺️ Mapa de alertas", "📄 Reporte"])

with tab1:
    st.subheader("Ingresa el polígono a analizar")
    metodo = st.radio("Método", ["Dibujar en mapa", "Subir archivo", "Coordenadas manuales"], horizontal=True)

    polygon = None

    if metodo == "Dibujar en mapa":
        st.info("Dibuja un polígono usando las herramientas de la izquierda del mapa")
        polygon = get_polygon_from_draw(center=[20.0, -102.0], zoom=6)

    elif metodo == "Subir archivo":
        uploaded = st.file_uploader("Sube tu archivo", type=["shp", "geojson", "kml", "zip"])
        if uploaded:
            polygon = get_polygon_from_file(uploaded)
            if polygon:
                st.success("Archivo cargado correctamente ✓")

    elif metodo == "Coordenadas manuales":
        st.markdown("Ingresa coordenadas en formato `latitud, longitud` (una por línea):")
        coords_text = st.text_area("Coordenadas", placeholder="20.123, -103.456\n20.124, -103.457\n20.120, -103.450", height=150)
        if st.button("Cargar coordenadas") and coords_text:
            polygon = get_polygon_from_coords(coords_text)
            if polygon:
                st.success("Polígono creado ✓")

    if polygon:
        st.session_state["polygon"] = polygon
        area = get_polygon_area_ha(polygon)
        st.metric("Área del polígono", f"{area:,.2f} ha")

        if st.button("🔍 Analizar deforestación", type="primary"):
            results = {"area_ha": area}
            progress = st.progress(0, text="Iniciando análisis...")

            if use_hansen:
                progress.progress(15, text="Consultando Hansen...")
                results["hansen"] = analyze_hansen(polygon, start_year - 2000, end_year - 2000)

            if use_glad:
                progress.progress(30, text="Consultando GLAD...")
                results["glad"] = analyze_glad(polygon)

            if use_jrc:
                progress.progress(50, text="Consultando JRC...")
                results["jrc"] = analyze_jrc_deforestation(polygon)

            if use_firms:
                progress.progress(65, text="Consultando FIRMS NASA...")
                results["firms"] = analyze_firms(polygon)

            if use_modis:
                progress.progress(80, text="Consultando MODIS Burn Area...")
                results["modis"] = analyze_modis_burn(polygon)

            if use_amazon:
                progress.progress(92, text="Consultando JRC Amazon...")
                results["amazon"] = analyze_jrc_amazon(polygon)

            progress.progress(100, text="¡Análisis completado!")
            st.session_state["results"] = results
            st.success("¡Listo! Ve a la pestaña 'Mapa de alertas'")

with tab2:
    st.subheader("Mapa de alertas")
    if "results" in st.session_state and "polygon" in st.session_state:
        results  = st.session_state["results"]
        polygon  = st.session_state["polygon"]
        hansen   = results.get("hansen", {})
        glad     = results.get("glad", {})
        jrc      = results.get("jrc", {})
        firms    = results.get("firms", {})
        modis    = results.get("modis", {})
        amazon   = results.get("amazon", {})

        # Métricas
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Área polígono",       f"{results['area_ha']:,.2f} ha")
        col2.metric("Hansen pérdida",      f"{hansen.get('total_loss_ha', 0):,.2f} ha")
        col3.metric("JRC deforestación",   f"{jrc.get('deforestation_ha', 0):,.2f} ha")
        col4.metric("JRC degradación",     f"{jrc.get('degradation_ha', 0):,.2f} ha")
        col5.metric("FIRMS incendios",     f"{firms.get('fire_area_ha', 0):,.2f} ha")

        col6, col7, col8 = st.columns(3)
        col6.metric("GLAD alertas",        f"{glad.get('alert_area_ha', 0):,.2f} ha")
        col7.metric("MODIS área quemada",  f"{modis.get('burn_area_ha', 0):,.2f} ha")
        col8.metric("Hansen ganancia",     f"{hansen.get('gain_ha', 0):,.2f} ha")

        # Mapa
        m = create_alert_map(polygon, results)
        st_folium(m, width=None, height=550, returned_objects=[])

        # Gráfica Hansen por año
        if hansen.get("by_year"):
            import pandas as pd
            st.subheader("Pérdida forestal anual (Hansen)")
            df = pd.DataFrame(hansen["by_year"])
            df.columns = ["Año", "Área perdida (ha)"]
            st.bar_chart(df.set_index("Año"))

        # JRC Amazon detalle
        if amazon:
            st.subheader("Cobertura forestal JRC Amazon")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Bosque intacto",   f"{amazon.get('undisturbed_ha', 0):,.2f} ha")
            col2.metric("Degradado",        f"{amazon.get('degraded_ha', 0):,.2f} ha")
            col3.metric("Deforestado",      f"{amazon.get('deforested_ha', 0):,.2f} ha")
            col4.metric("Regeneración",     f"{amazon.get('regrowth_ha', 0):,.2f} ha")

        # Notas de fuentes con errores
        for source, data in [("GLAD", glad), ("JRC", jrc), ("FIRMS", firms), ("MODIS", modis)]:
            if data.get("note"):
                st.warning(f"⚠️ {source}: {data['note']}")
    else:
        st.info("Primero ingresa y analiza un polígono en la pestaña 'Polígono'")

with tab3:
    st.subheader("Generar reporte")
    if "results" in st.session_state and "polygon" in st.session_state:
        results = st.session_state["results"]
        polygon = st.session_state["polygon"]
        hansen  = results.get("hansen", {})
        glad    = results.get("glad", {})
        jrc     = results.get("jrc", {})
        firms   = results.get("firms", {})
        modis   = results.get("modis", {})

        col1, col2 = st.columns(2)
        with col1:
            if st.button("📄 Generar PDF"):
                pdf = generate_pdf(results["area_ha"], hansen, glad, jrc, polygon.wkt, firms, modis)
                st.download_button("⬇️ Descargar PDF", pdf,
                                   "reporte_deforestacion.pdf", "application/pdf")
        with col2:
            if st.button("📊 Generar Excel"):
                excel = generate_excel(results["area_ha"], hansen, glad, jrc, firms, modis)
                st.download_button("⬇️ Descargar Excel", excel,
                                   "reporte_deforestacion.xlsx",
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.info("Primero ingresa y analiza un polígono en la pestaña 'Polígono'")