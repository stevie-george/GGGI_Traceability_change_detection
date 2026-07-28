import datetime
import streamlit as st
from streamlit_folium import st_folium
import pandas as pd
import plotly.graph_objects as go

from modules.polygon_input import get_polygon_from_draw, get_polygon_from_file, get_polygon_from_coords
from modules.gee_analysis import (initialize_gee, analyze_hansen, analyze_glad,
                                   analyze_jrc_deforestation, analyze_firms,
                                   analyze_modis_burn, analyze_jrc_amazon,
                                   get_polygon_area_ha, HANSEN_ASSET, JRC_TMF_YEAR)
from modules.map_viewer import create_alert_map
from modules.report_generator import generate_pdf, generate_excel

CURRENT_YEAR = datetime.date.today().year

# Año de la versión de Hansen, extraído del ID del asset (p. ej. ..._2025_v1_13).
try:
    HANSEN_YEAR = int(HANSEN_ASSET.split("global_forest_change_")[1].split("_")[0])
except (IndexError, ValueError):
    HANSEN_YEAR = CURRENT_YEAR

st.set_page_config(page_title="Sistema de Consenso en Pérdida de Cobertura", page_icon="🌿", layout="wide")

st.markdown("""
    <style>
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 0rem !important;
            padding-left: 0.8rem !important;
            padding-right: 0.8rem !important;
            max-width: 100% !important;
        }
    </style>
""", unsafe_allow_html=True)

st.markdown("# 🌿 Sistema de Consenso en Pérdida de Cobertura")
st.caption("Consenso multi-fuente de pérdida de cobertura forestal — cultivos de aguacate y agave tequilana en México")

with st.sidebar:
    st.header("⚙️ Configuración")
    cultivo    = st.selectbox("Cultivo", ["Aguacate", "Agave tequilana", "Otro"])
    start_year = st.slider("Año inicio", 2001, CURRENT_YEAR, 2015)
    end_year   = st.slider("Año fin",    2001, CURRENT_YEAR, CURRENT_YEAR)

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

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📍 Polígono",
    "🗺️ Mapa de alertas",
    "📄 Reporte",
    "⚙️ Configuración",
    "🗂️ Ingresar fuente",
    "✅ Validación"
])

# ══════════════════════════════════════════════════════════
# TAB 1 — POLÍGONO
# ══════════════════════════════════════════════════════════
with tab1:
    metodo = st.radio("Método de ingreso",
                      ["Dibujar en mapa", "Subir archivo", "Coordenadas manuales"],
                      horizontal=True)

    if metodo == "Dibujar en mapa":
        st.caption("Dibuja un polígono con las herramientas de la izquierda. Botón ⛶ para pantalla completa.")
        get_polygon_from_draw(center=[20.0, -102.0], zoom=6)

    elif metodo == "Subir archivo":
        uploaded = st.file_uploader(
            "Sube tu archivo",
            type=["zip", "geojson", "kml"],
            help="Para shapefiles: comprime .shp, .dbf, .shx y .prj en un .zip"
        )
        if uploaded:
            polygon_file = get_polygon_from_file(uploaded)
            if polygon_file:
                st.session_state["polygon"] = polygon_file
                st.success("Archivo cargado ✓")

    elif metodo == "Coordenadas manuales":
        st.markdown("Ingresa coordenadas en formato `latitud, longitud` (una por línea):")
        coords_text = st.text_area("Coordenadas",
            placeholder="20.123, -103.456\n20.124, -103.457\n20.120, -103.450",
            height=150)
        if st.button("Cargar coordenadas") and coords_text:
            polygon_coords = get_polygon_from_coords(coords_text)
            if polygon_coords:
                st.session_state["polygon"] = polygon_coords
                st.success("Polígono creado ✓")

    if "polygon" in st.session_state:
        st.divider()
        area = get_polygon_area_ha(st.session_state["polygon"])
        col_a, col_b = st.columns([1, 3])
        with col_a:
            st.metric("Área", f"{area:,.2f} ha")
        with col_b:
            analizar = st.button("🔍 Analizar deforestación", type="primary", key="btn_analizar")

        if analizar:
            polygon = st.session_state["polygon"]
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
            st.success("¡Listo! Ve a la pestaña **Mapa de alertas**")
# ══════════════════════════════════════════════════════════
# TAB 2 — MAPA DE ALERTAS + DASHBOARD
# ══════════════════════════════════════════════════════════
with tab2:
    if "results" in st.session_state and "polygon" in st.session_state:
        results = st.session_state["results"]
        polygon = st.session_state["polygon"]
        hansen  = results.get("hansen", {})
        glad    = results.get("glad", {})
        jrc     = results.get("jrc", {})
        firms   = results.get("firms", {})
        modis   = results.get("modis", {})
        amazon  = results.get("amazon", {})

        # Mapa grande con basemaps satelite
        m = create_alert_map(polygon, results)
        st_folium(m, height=1100,
                  returned_objects=[], width='stretch')

        st.divider()

        # ── Dashboard métricas ────────────────────────────────────────
        st.markdown("### 📊 Resumen de alertas")

        # Fila 1 — Deforestación
        st.markdown("**🌳 Cobertura forestal**")
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Área polígono",     f"{results['area_ha']:,.2f} ha")
        col2.metric("Hansen pérdida",    f"{hansen.get('total_loss_ha', 0):,.2f} ha",
                    delta=f"{round(hansen.get('total_loss_ha', 0)/results['area_ha']*100, 2) if results['area_ha'] else 0}%",
                    delta_color="inverse")
        col3.metric("Hansen ganancia",   f"{hansen.get('gain_ha', 0):,.2f} ha",
                    delta_color="normal")
        col4.metric("JRC deforestación", f"{jrc.get('deforestation_ha', 0):,.2f} ha",
                    delta_color="inverse")
        col5.metric("JRC degradación",   f"{jrc.get('degradation_ha', 0):,.2f} ha",
                    delta_color="inverse")

        # Fila 2 — Alertas e incendios
        st.markdown("**🔥 Alertas e incendios**")
        col6, col7, col8, col9 = st.columns(4)
        col6.metric("GLAD alertas",    f"{glad.get('alert_area_ha', 0):,.2f} ha",  delta_color="inverse")
        col7.metric("FIRMS incendios", f"{firms.get('fire_area_ha', 0):,.2f} ha",  delta_color="inverse")
        col8.metric("MODIS quemado",   f"{modis.get('burn_area_ha', 0):,.2f} ha",  delta_color="inverse")
        col9.metric("JRC regrowth",    f"{jrc.get('regrowth_ha', 0):,.2f} ha",     delta_color="normal")

        # Fila 3 — JRC Amazon (si disponible)
        if amazon:
            st.markdown("**🌎 Cobertura JRC Amazon**")
            col_a, col_b, col_c, col_d = st.columns(4)
            col_a.metric("Bosque intacto",  f"{amazon.get('undisturbed_ha', 0):,.2f} ha")
            col_b.metric("Degradado",       f"{amazon.get('degraded_ha', 0):,.2f} ha",    delta_color="inverse")
            col_c.metric("Deforestado",     f"{amazon.get('deforested_ha', 0):,.2f} ha",  delta_color="inverse")
            col_d.metric("Regeneración",    f"{amazon.get('regrowth_ha', 0):,.2f} ha",    delta_color="normal")

        st.divider()

        # ── Gráficas ──────────────────────────────────────────────────
        col_left, col_right = st.columns(2)

        with col_left:
            st.markdown("### 🌳 Pérdidas y ganancias forestales")
            hansen_by_year = {r["year"]: r["area_ha"] for r in hansen.get("by_year", [])}
            jrc_defor      = {r["year"]: r["area_ha"] for r in jrc.get("by_year_defor", [])}
            jrc_regrowth   = {r["year"]: r["area_ha"] for r in jrc.get("by_year_regrowth", [])}
            all_years = sorted(set(
                list(hansen_by_year.keys()) +
                list(jrc_defor.keys()) +
                list(jrc_regrowth.keys())
            ))
            if all_years:
                fig1 = go.Figure()
                fig1.add_trace(go.Scatter(
                    x=all_years, y=[hansen_by_year.get(y, 0) for y in all_years],
                    name="Hansen — pérdida", line=dict(color="#ff4d4d", width=2), marker=dict(size=6)
                ))
                fig1.add_trace(go.Scatter(
                    x=all_years, y=[jrc_defor.get(y, 0) for y in all_years],
                    name="JRC — deforestación", line=dict(color="#cc66ff", width=2), marker=dict(size=6)
                ))
                fig1.add_trace(go.Scatter(
                    x=all_years, y=[jrc_regrowth.get(y, 0) for y in all_years],
                    name="JRC — regrowth", line=dict(color="#2ecc71", width=2, dash="dash"), marker=dict(size=6)
                ))
                fig1.update_layout(
                    xaxis_title="Año", yaxis_title="Área (ha)",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                    height=380, margin=dict(l=20, r=20, t=40, b=20),
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="white")
                )
                st.plotly_chart(fig1, use_container_width="")
            else:
                st.info("Sin datos anuales disponibles.")

        with col_right:
            st.markdown("### 🔥 Incendios y área quemada")
            firms_by_year = {r["year"]: r["area_ha"] for r in firms.get("by_year", [])}
            modis_by_year = {r["year"]: r["area_ha"] for r in modis.get("by_year", [])}
            all_years_fire = sorted(set(
                list(firms_by_year.keys()) +
                list(modis_by_year.keys())
            ))
            if all_years_fire:
                fig2 = go.Figure()
                fig2.add_trace(go.Bar(
                    x=all_years_fire, y=[firms_by_year.get(y, 0) for y in all_years_fire],
                    name="FIRMS — incendios", marker_color="#ffcc00", opacity=0.85
                ))
                fig2.add_trace(go.Bar(
                    x=all_years_fire, y=[modis_by_year.get(y, 0) for y in all_years_fire],
                    name="MODIS — área quemada", marker_color="#ff3333", opacity=0.85
                ))
                fig2.update_layout(
                    barmode="group", xaxis_title="Año", yaxis_title="Área (ha)",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                    height=380, margin=dict(l=20, r=20, t=40, b=20),
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="white")
                )
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("Sin datos de incendios disponibles.")

        for source, data in [("GLAD", glad), ("JRC", jrc), ("FIRMS", firms), ("MODIS", modis)]:
            if data.get("note"):
                st.warning(f"⚠️ {source}: {data['note']}")
    else:
        st.info("Primero ingresa y analiza un polígono en la pestaña **Polígono**")

# ══════════════════════════════════════════════════════════
# TAB 3 — REPORTE
# ══════════════════════════════════════════════════════════
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
        st.info("Primero ingresa y analiza un polígono en la pestaña **Polígono**")

# ══════════════════════════════════════════════════════════
# TAB 4 — CONFIGURACIÓN / CREDENCIALES GEE
# ══════════════════════════════════════════════════════════
with tab4:
    st.subheader("⚙️ Configuración de credenciales GEE por estado")
    st.info("Esta sección permite configurar cuentas de Google Earth Engine independientes para cada estado de la República Mexicana.")

    st.markdown("### Estado actual de conexión")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Proyecto GEE activo", "ee-stephaniegeorge")
        st.metric("Estado de conexión", "Conectado ✓" if gee_ok else "Desconectado ✗")
    with col2:
        st.metric("Service Account", "gee-streamlit@ee-stephaniegeorge")
        st.metric("Tier", "Contributor")

    st.divider()
    st.markdown("### Agregar credenciales por estado")

    estados = [
        "Jalisco", "Michoacán", "Nayarit", "Colima", "Aguascalientes",
        "Zacatecas", "Guanajuato", "Querétaro", "Estado de México",
        "Morelos", "Puebla", "Oaxaca", "Chiapas", "Veracruz", "Yucatán",
        "Campeche", "Quintana Roo", "Tabasco", "Guerrero", "Hidalgo",
        "San Luis Potosí", "Tamaulipas", "Nuevo León", "Coahuila",
        "Chihuahua", "Sonora", "Sinaloa", "Durango", "Baja California",
        "Baja California Sur", "Tlaxcala", "CDMX"
    ]

    col1, col2 = st.columns(2)
    with col1:
        estado_sel  = st.selectbox("Estado", estados)
        proyecto_id = st.text_input("Project ID de GEE", placeholder="ee-nombre-proyecto")
        svc_account = st.text_input("Service Account email", placeholder="nombre@proyecto.iam.gserviceaccount.com")
    with col2:
        credentials_json = st.text_area(
            "Credenciales JSON (Service Account Key)", height=150,
            placeholder='{\n  "type": "service_account",\n  "project_id": "...",\n  ...\n}'
        )

    st.button("💾 Guardar credenciales", disabled=True)
    st.caption("⚠️ Funcionalidad en desarrollo — disponible en v2.0")

    st.divider()
    st.markdown("### Credenciales configuradas por estado")
    st.dataframe({
        "Estado":          ["—"],
        "Proyecto GEE":    ["—"],
        "Service Account": ["—"],
        "Estatus":         ["Sin configurar"],
    }, use_container_width=True)

# ══════════════════════════════════════════════════════════
# TAB 5 — FUENTES DE DATOS
# ══════════════════════════════════════════════════════════
with tab5:
    st.subheader("🗂️ Fuentes de datos y capas adicionales")
    st.info("Esta sección permitirá incorporar nuevas fuentes de datos satelitales y capas de uso de suelo para enriquecer el análisis.")

    st.markdown("### Fuentes de deforestación activas")
    st.dataframe({
        "Fuente":             ["Hansen GFC", "GLAD Alerts", "JRC TMF", "FIRMS NASA", "MODIS MCD64A1"],
        "Tipo":               ["Pérdida forestal", "Alertas", "Deforestación/Degradación", "Incendios activos", "Área quemada"],
        "Resolución":         ["30m", "10m", "30m", "1km", "500m"],
        "Cobertura temporal": [f"2000–{HANSEN_YEAR}", "2019–presente", f"1990–{JRC_TMF_YEAR}",
                               "2000–presente", "2000–presente"],
        "Estado":             ["✅ Activa", "✅ Activa", "✅ Activa", "✅ Activa", "✅ Activa"],
    }, use_container_width=True)

    st.divider()
    st.markdown("### Capas de uso de suelo (próximamente)")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 🌱 Capas en desarrollo")
        for nombre in [
            "SIAP — Superficie agrícola por cultivo",
            "INEGI Serie VII — Uso de suelo y vegetación",
            "MapBiomas México — Clasificación anual",
            "NALCMS — North American Land Change",
            "RAN — Registro Agrario Nacional (parcelas)",
        ]:
            st.markdown(f"🔲 **{nombre}** — *En desarrollo*")
    with col2:
        st.markdown("#### 🔥 Capas de riesgo adicionales")
        for nombre in [
            "CONABIO — Áreas Naturales Protegidas",
            "CONAFOR — Inventario Nacional Forestal",
            "CONANP — Regiones Prioritarias",
            "Global Forest Watch — Integridad forestal",
            "WWF — Ecorregiones terrestres",
        ]:
            st.markdown(f"🔲 **{nombre}** — *En desarrollo*")

    st.divider()
    st.markdown("### Agregar nueva fuente de datos")
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Nombre de la fuente", placeholder="Ej. INEGI Serie VII")
        st.text_input("Asset ID en GEE", placeholder="Ej. INEGI/USVI/2017")
        st.selectbox("Tipo de dato", ["ImageCollection", "Image", "FeatureCollection", "Table"])
    with col2:
        st.text_input("Banda principal", placeholder="Ej. landcover")
        st.text_input("Descripción", placeholder="Breve descripción de la fuente")
        st.color_picker("Color en mapa", "#FF5733")

    st.button("➕ Agregar fuente", disabled=True)
    st.caption("⚠️ Funcionalidad en desarrollo — disponible en v2.0")

# ══════════════════════════════════════════════════════════
# TAB 6 — VALIDACIÓN
# ══════════════════════════════════════════════════════════
with tab6:
    st.subheader("✅ Validación y precisión del sistema")
    st.info("Esta sección reportará las métricas de precisión del sistema de detección de deforestación, siguiendo el marco metodológico de Olofsson et al. (2014).")

    st.markdown("### Marco metodológico")
    col1, col2, col3 = st.columns(3)
    col1.metric("Marco de referencia",  "Olofsson et al. 2014")
    col2.metric("Método de muestreo",   "Estratificado aleatorio")
    col3.metric("Unidad de validación", "Puntos de referencia")

    st.divider()
    st.markdown("### Métricas de precisión por fuente (pendiente)")
    st.dataframe({
        "Fuente":                   ["Hansen GFC", "GLAD Alerts", "JRC TMF", "FIRMS NASA", "MODIS MCD64A1"],
        "Precisión global (OA)":    ["—", "—", "—", "—", "—"],
        "Precisión productor (PA)": ["—", "—", "—", "—", "—"],
        "Precisión usuario (UA)":   ["—", "—", "—", "—", "—"],
        "F1-Score":                 ["—", "—", "—", "—", "—"],
        "N puntos validados":       ["0", "0", "0", "0", "0"],
        "Última actualización":     ["Pendiente"] * 5,
    }, use_container_width=True)

    st.divider()
    st.markdown("### Matriz de confusión")
    col1, col2 = st.columns(2)
    with col1:
        st.selectbox("Fuente a validar", ["Hansen GFC", "GLAD Alerts", "JRC TMF", "FIRMS NASA", "MODIS MCD64A1"])
        st.selectbox("Período de validación", ["2015–2020", "2020–2023", "2023–2024"])
        st.number_input("N puntos de validación", min_value=0, value=0)
    with col2:
        st.markdown("#### Matriz de confusión (vacía)")
        st.dataframe({
            "":                         ["Deforestación (ref.)", "No deforestación (ref.)"],
            "Deforestación (pred.)":    ["—", "—"],
            "No deforestación (pred.)": ["—", "—"],
        }, use_container_width=True)

    st.divider()
    st.markdown("### Cargar datos de validación")
    col1, col2 = st.columns(2)
    with col1:
        st.file_uploader("Subir puntos de validación (CSV/GeoJSON)", type=["csv", "geojson"], disabled=True)
    with col2:
        st.file_uploader("Subir matriz de confusión (Excel)", type=["xlsx"], disabled=True)

    st.button("📊 Calcular métricas", disabled=True)
    st.caption("⚠️ Funcionalidad en desarrollo — disponible en v2.0")