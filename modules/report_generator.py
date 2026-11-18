import io
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, Image
from reportlab.lib.units import inch
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")
from datetime import datetime

COLORS = {
    "Hansen":         "#e74c3c",
    "GLAD":           "#e67e22",
    "JRC Defor":      "#8e44ad",
    "JRC Degrad":     "#d35400",
    "MODIS":          "#c0392b",
    "Regrowth":       "#27ae60",
    "Promedio Defor": "#2c3e50",
    "Promedio Fuego": "#7f8c8d",
}

def rows_to_dict(rows, yr_key="year", area_key="area_ha"):
    return {r[yr_key]: r[area_key] for r in rows} if rows else {}

def styled_table(data_rows, col_widths):
    t = Table(data_rows, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0), colors.HexColor("#1a5276")),
        ("TEXTCOLOR",      (0, 0), (-1, 0), colors.white),
        ("FONTNAME",       (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID",           (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eaf4fb")]),
        ("FONTSIZE",       (0, 0), (-1, -1), 8),
        ("PADDING",        (0, 0), (-1, -1), 5),
    ]))
    return t

def make_bar_chart(title, labels, values, color):
    fig, ax = plt.subplots(figsize=(6, 2.8))
    ax.bar(labels, values, color=color, alpha=0.85)
    ax.set_title(title, fontsize=11)
    ax.set_ylabel("Área (ha)")
    plt.xticks(rotation=45, ha="right", fontsize=8)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150)
    plt.close(); buf.seek(0)
    return buf

def make_multiline_chart(datasets_by_year, title, prom_key="Promedio"):
    all_years = sorted(set(y for k, d in datasets_by_year.items()
                           if k != prom_key for y in d.keys()))
    if not all_years:
        return None
    fig, ax = plt.subplots(figsize=(7, 4))
    for name, year_data in datasets_by_year.items():
        if name == prom_key:
            continue
        ys = [year_data.get(y, 0) for y in all_years]
        ax.plot(all_years, ys, marker="o", label=name,
                color=COLORS.get(name, "#888"), linewidth=2, markersize=5)
    if prom_key in datasets_by_year:
        prom = [datasets_by_year[prom_key].get(y, 0) for y in all_years]
        ax.plot(all_years, prom, marker="s", label=prom_key,
                color="#2c3e50", linewidth=2.5, markersize=6,
                linestyle="--", zorder=5)
    ax.set_title(title, fontsize=11)
    ax.set_ylabel("Área (ha)")
    ax.set_xlabel("Año")
    ax.set_xticks(all_years)
    ax.legend(fontsize=8, loc="upper left")
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150)
    plt.close(); buf.seek(0)
    return buf

def make_comparative_section(story, heading_style, section_title,
                              datasets_by_year, prom_label):
    """Genera tabla comparativa + gráfica de líneas para un grupo de datasets."""
    datasets_by_year = {k: v for k, v in datasets_by_year.items() if v}
    if not datasets_by_year:
        return

    all_years = sorted(set(y for d in datasets_by_year.values() for y in d.keys()))
    if not all_years:
        return

    ds_names = list(datasets_by_year.keys())
    story.append(Paragraph(section_title, heading_style))

    # Tabla
    header = ["Año"] + ds_names + [prom_label]
    table_rows = [header]
    prom_by_year = {}
    for y in all_years:
        vals = [datasets_by_year[ds].get(y, 0) for ds in ds_names]
        avg  = round(sum(vals) / len(vals), 4)
        prom_by_year[y] = avg
        table_rows.append([str(y)] + [f"{v:,.4f}" for v in vals] + [f"{avg:,.4f}"])

    n_cols = len(header)
    col_w  = [0.65*inch] + [1.1*inch] * (n_cols - 2) + [1.0*inch]
    story.append(styled_table(table_rows, col_w))
    story.append(Spacer(1, 0.15*inch))

    # Gráfica líneas + promedio punteado
    plot_data = dict(datasets_by_year)
    plot_data[prom_label] = prom_by_year
    buf = make_multiline_chart(plot_data, section_title, prom_key=prom_label)
    if buf:
        story.append(Image(buf, width=6.5*inch, height=3.5*inch))
    story.append(Spacer(1, 0.2*inch))


def generate_pdf(polygon_area_ha, hansen, glad, jrc, polygon_wkt,
                 modis=None, lulc=None, defor_lulc=None):
    modis = modis or {}
    lulc = lulc or {}
    defor_lulc = defor_lulc or {}
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            rightMargin=0.75*inch, leftMargin=0.75*inch,
                            topMargin=inch, bottomMargin=inch)
    styles = getSampleStyleSheet()
    title_style   = ParagraphStyle("tt", parent=styles["Title"],
                                   fontSize=17, textColor=colors.HexColor("#1a5276"))
    heading_style = ParagraphStyle("hh", parent=styles["Heading2"],
                                   fontSize=12, textColor=colors.HexColor("#1a5276"))
    sub_style     = ParagraphStyle("ss", parent=styles["Heading3"],
                                   fontSize=11, textColor=colors.HexColor("#1a5276"))
    story = []

    # ── Portada ───────────────────────────────────────────────────────
    story.append(Paragraph("Sistema de Consenso en Pérdida de Cobertura", title_style))
    story.append(Paragraph(f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                            styles["Normal"]))
    story.append(Spacer(1, 0.2*inch))

    # ── 1. Resumen ejecutivo ──────────────────────────────────────────
    pct = round(hansen.get("total_loss_ha", 0) / polygon_area_ha * 100, 2) \
          if polygon_area_ha > 0 else 0
    story.append(Paragraph("1. Resumen ejecutivo", heading_style))
    sr = [
        ["Fuente", "Indicador", "Área (ha)"],
        ["Polígono", "Área total",               f"{polygon_area_ha:,.2f}"],
        ["Hansen",   "Pérdida forestal",          f"{hansen.get('total_loss_ha',0):,.4f}"],
        ["Hansen",   "Ganancia forestal",         f"{hansen.get('gain_ha',0):,.4f}"],
        ["GLAD",     "Alertas deforestación",     f"{glad.get('alert_area_ha',0):,.4f}"],
        ["JRC",      "Deforestación acumulada",   f"{jrc.get('deforestation_ha',0):,.4f}"],
        ["JRC",      "Degradación acumulada",     f"{jrc.get('degradation_ha',0):,.4f}"],
        ["JRC",      "Regrowth acumulado",        f"{jrc.get('regrowth_ha',0):,.4f}"],
        ["MODIS",    "Área quemada",              f"{modis.get('burn_area_ha',0):,.4f}"],
    ]
    if lulc.get("by_class"):
        sr.append(["COBIOCOM", "Aguacate (clasificación)", f"{lulc.get('aguacate_ha',0):,.4f}"])
        sr.append(["COBIOCOM", "Agave (clasificación)",    f"{lulc.get('agave_ha',0):,.4f}"])
    if defor_lulc.get("by_class"):
        sr.append(["Hansen×LULC", "Deforestación neta (excl. agrícola/urbano)",
                   f"{defor_lulc.get('net_ha',0):,.4f}"])
    sr.append(["Hansen", "% área afectada", f"{pct:.2f}%"])
    story.append(styled_table(sr, [1.3*inch, 2.7*inch, 2*inch]))
    story.append(Spacer(1, 0.2*inch))

    # ── 2. Gráficas de barras ─────────────────────────────────────────
    story.append(Paragraph("2. Pérdida anual por dataset", heading_style))
    story.append(Spacer(1, 0.1*inch))

    bar_configs = [
        ("Hansen — pérdida forestal",     hansen.get("by_year", []),         "Hansen"),
        ("JRC — deforestación anual",     jrc.get("by_year_defor", []),      "JRC Defor"),
        ("JRC — degradación anual",       jrc.get("by_year_degrad", []),     "JRC Degrad"),
        ("JRC — regrowth anual",          jrc.get("by_year_regrowth", []),   "Regrowth"),
        ("MODIS — área quemada anual",    modis.get("by_year", []),          "MODIS"),
    ]
    for title, rows, ds_name in bar_configs:
        if rows:
            labels = [str(r["year"]) for r in rows]
            values = [r["area_ha"] for r in rows]
            buf = make_bar_chart(title, labels, values, COLORS[ds_name])
            story.append(Image(buf, width=5*inch, height=2.5*inch))
            story.append(Spacer(1, 0.1*inch))

    # ── 3. Comparativa deforestación ─────────────────────────────────
    defor_datasets = {
        "Hansen":    rows_to_dict(hansen.get("by_year", [])),
        "JRC Defor": rows_to_dict(jrc.get("by_year_defor", [])),
        "JRC Degrad":rows_to_dict(jrc.get("by_year_degrad", [])),
        "GLAD":      {}, # GLAD no tiene by_year aún
    }
    make_comparative_section(
        story, heading_style,
        "3. Comparativa anual — deforestación y degradación",
        defor_datasets, "Promedio Defor"
    )

    # ── 4. Regrowth ───────────────────────────────────────────────────
    regrowth_datasets = {
        "Regrowth": rows_to_dict(jrc.get("by_year_regrowth", [])),
    }
    make_comparative_section(
        story, heading_style,
        "4. Regeneración forestal (Regrowth JRC)",
        regrowth_datasets, "Promedio"
    )

    # ── 5. Área quemada ───────────────────────────────────────────────
    fire_datasets = {
        "MODIS": rows_to_dict(modis.get("by_year", [])),
    }
    make_comparative_section(
        story, heading_style,
        "5. Área quemada anual (MODIS)",
        fire_datasets, "Promedio Fuego"
    )

    # ── 6. Clasificación COBIOCOM LULC (si cae dentro del área) ───────
    lulc_rows = [c for c in lulc.get("by_class", []) if c.get("area_ha", 0) > 0]
    if lulc_rows:
        story.append(Paragraph("6. Clasificación COBIOCOM LULC (RF v6, 2025)", heading_style))
        tbl = [["Clase", "Área (ha)", "% del polígono"]]
        for c in lulc_rows:
            pctc = round(c["area_ha"] / polygon_area_ha * 100, 2) if polygon_area_ha else 0
            tbl.append([c["name"], f"{c['area_ha']:,.4f}", f"{pctc:.2f}%"])
        story.append(styled_table(tbl, [2.7*inch, 1.8*inch, 1.5*inch]))
        story.append(Spacer(1, 0.2*inch))

    # ── 7. Deforestación por clase de cobertura (intersección) ────────
    dfx_rows = sorted([c for c in defor_lulc.get("by_class", []) if c.get("area_ha", 0) > 0],
                      key=lambda c: -c["area_ha"])
    if dfx_rows:
        total = defor_lulc.get("total_ha", 0) or 0
        excl_ids = defor_lulc.get("exclude_ids", [])
        story.append(Paragraph("7. Deforestación por clase de cobertura (LULC)", heading_style))
        tbl = [["Clase", "Deforestación (ha)", "% de la pérdida", "Excluida"]]
        for c in dfx_rows:
            pctl = round(c["area_ha"] / total * 100, 1) if total else 0
            tbl.append([c["name"], f"{c['area_ha']:,.4f}", f"{pctl:.1f}%",
                        "sí" if c["class_id"] in excl_ids else "—"])
        story.append(styled_table(tbl, [2.3*inch, 1.6*inch, 1.3*inch, 0.8*inch]))
        story.append(Spacer(1, 0.08*inch))
        story.append(Paragraph(
            f"<font size=8>Total sobre área clasificada: {total:,.4f} ha &nbsp;|&nbsp; "
            f"excluida agrícola/urbano ({', '.join(defor_lulc.get('exclude_names', []))}): "
            f"{defor_lulc.get('excluded_ha', 0):,.4f} ha &nbsp;|&nbsp; "
            f"<b>deforestación neta: {defor_lulc.get('net_ha', 0):,.4f} ha</b></font>",
            styles["Normal"]))
        story.append(Spacer(1, 0.1*inch))
        buf = make_bar_chart("Deforestación por clase de cobertura (ha)",
                             [c["name"] for c in dfx_rows],
                             [c["area_ha"] for c in dfx_rows], "#c0392b")
        story.append(Image(buf, width=5.5*inch, height=2.6*inch))
        story.append(Spacer(1, 0.2*inch))

    # ── 8. Geometría ─────────────────────────────────────────────────
    story.append(Paragraph("8. Geometría del polígono (WKT)", heading_style))
    story.append(Paragraph(
        f"<font size=7>{polygon_wkt[:600]}...</font>", styles["Normal"]))

    doc.build(story)
    buffer.seek(0)
    return buffer


def generate_excel(polygon_area_ha, hansen, glad, jrc, modis=None, lulc=None,
                   defor_lulc=None):
    modis = modis or {}
    lulc = lulc or {}
    defor_lulc = defor_lulc or {}
    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        # Resumen
        resumen = {
            "Área polígono (ha)":     polygon_area_ha,
            "Hansen pérdida (ha)":    hansen.get("total_loss_ha", 0),
            "Hansen ganancia (ha)":   hansen.get("gain_ha", 0),
            "GLAD alertas (ha)":      glad.get("alert_area_ha", 0),
            "JRC deforestación (ha)": jrc.get("deforestation_ha", 0),
            "JRC degradación (ha)":   jrc.get("degradation_ha", 0),
            "JRC regrowth (ha)":      jrc.get("regrowth_ha", 0),
            "MODIS quemado (ha)":     modis.get("burn_area_ha", 0),
            "% área afectada":        round(hansen.get("total_loss_ha", 0) /
                                            polygon_area_ha * 100, 2)
                                      if polygon_area_ha > 0 else 0,
        }
        if lulc.get("by_class"):
            resumen["Aguacate COBIOCOM (ha)"] = lulc.get("aguacate_ha", 0)
            resumen["Agave COBIOCOM (ha)"]    = lulc.get("agave_ha", 0)
        if defor_lulc.get("by_class"):
            resumen["Deforestación clasificada (ha)"]       = defor_lulc.get("total_ha", 0)
            resumen["Deforestación excl. agrícola/urbano (ha)"] = defor_lulc.get("excluded_ha", 0)
            resumen["Deforestación NETA (ha)"]              = defor_lulc.get("net_ha", 0)
        pd.DataFrame([resumen]).to_excel(writer, sheet_name="Resumen", index=False)

        # Clasificación COBIOCOM LULC (clases dentro del área)
        lulc_rows = [c for c in lulc.get("by_class", []) if c.get("area_ha", 0) > 0]
        if lulc_rows:
            pd.DataFrame([{
                "Clase": c["name"],
                "Área (ha)": round(c["area_ha"], 4),
                "% polígono": round(c["area_ha"] / polygon_area_ha * 100, 2) if polygon_area_ha else 0,
            } for c in lulc_rows]).to_excel(writer, sheet_name="COBIOCOM LULC", index=False)

        # Deforestación x LULC (intersección por clase)
        dfx_rows = [c for c in defor_lulc.get("by_class", []) if c.get("area_ha", 0) > 0]
        if dfx_rows:
            total = defor_lulc.get("total_ha", 0) or 0
            excl_ids = defor_lulc.get("exclude_ids", [])
            pd.DataFrame([{
                "Clase": c["name"],
                "Deforestación (ha)": round(c["area_ha"], 4),
                "% de la pérdida": round(c["area_ha"] / total * 100, 2) if total else 0,
                "Excluida (agrícola/urbano)": "sí" if c["class_id"] in excl_ids else "no",
            } for c in sorted(dfx_rows, key=lambda c: -c["area_ha"])]).to_excel(
                writer, sheet_name="Deforestación x LULC", index=False)

        # Comparativa deforestación
        defor_ds = {
            "Hansen":    rows_to_dict(hansen.get("by_year", [])),
            "JRC Defor": rows_to_dict(jrc.get("by_year_defor", [])),
            "JRC Degrad":rows_to_dict(jrc.get("by_year_degrad", [])),
        }
        defor_ds = {k: v for k, v in defor_ds.items() if v}
        all_years_d = sorted(set(y for d in defor_ds.values() for y in d.keys()))
        if all_years_d:
            rows = []
            for y in all_years_d:
                row = {"Año": y}
                vals = []
                for ds in defor_ds:
                    v = defor_ds[ds].get(y, 0)
                    row[ds] = v
                    vals.append(v)
                row["Promedio Defor"] = round(sum(vals) / len(vals), 4)
                rows.append(row)
            cols = ["Año"] + list(defor_ds.keys()) + ["Promedio Defor"]
            pd.DataFrame(rows)[cols].to_excel(
                writer, sheet_name="Comparativa deforestación", index=False)

        # Regrowth
        rg = rows_to_dict(jrc.get("by_year_regrowth", []))
        if rg:
            pd.DataFrame([{"Año": y, "Regrowth (ha)": v}
                          for y, v in rg.items()]).to_excel(
                writer, sheet_name="Regrowth", index=False)

        # Área quemada (MODIS)
        burn = rows_to_dict(modis.get("by_year", []))
        if burn:
            pd.DataFrame([{"Año": y, "Área quemada (ha)": v}
                          for y, v in burn.items()]).to_excel(
                writer, sheet_name="Área quemada MODIS", index=False)

        # Hojas individuales
        for sheet_name, rows in [
            ("Hansen anual",     hansen.get("by_year", [])),
            ("JRC defor anual",  jrc.get("by_year_defor", [])),
            ("JRC degrad anual", jrc.get("by_year_degrad", [])),
            ("JRC regrowth",     jrc.get("by_year_regrowth", [])),
            ("MODIS anual",      modis.get("by_year", [])),
        ]:
            if rows:
                df = pd.DataFrame(rows)
                df.columns = ["Año", "Área (ha)"]
                df.to_excel(writer, sheet_name=sheet_name, index=False)

    buffer.seek(0)
    return buffer