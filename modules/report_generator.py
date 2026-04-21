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
    "FIRMS":          "#f39c12",
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
                 firms=None, modis=None):
    firms = firms or {}
    modis = modis or {}
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
    story.append(Paragraph("Reporte de Alertas de Deforestación", title_style))
    story.append(Paragraph(f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                            styles["Normal"]))
    story.append(Spacer(1, 0.2*inch))

    # ── 1. Resumen ejecutivo ──────────────────────────────────────────
    pct = round(hansen.get("total_loss_ha", 0) / polygon_area_ha * 100, 2) \
          if polygon_area_ha > 0 else 0
    story.append(Paragraph("1. Resumen ejecutivo", heading_style))
    story.append(styled_table([
        ["Fuente", "Indicador", "Área (ha)"],
        ["Polígono", "Área total",               f"{polygon_area_ha:,.2f}"],
        ["Hansen",   "Pérdida forestal",          f"{hansen.get('total_loss_ha',0):,.4f}"],
        ["Hansen",   "Ganancia forestal",         f"{hansen.get('gain_ha',0):,.4f}"],
        ["GLAD",     "Alertas deforestación",     f"{glad.get('alert_area_ha',0):,.4f}"],
        ["JRC",      "Deforestación acumulada",   f"{jrc.get('deforestation_ha',0):,.4f}"],
        ["JRC",      "Degradación acumulada",     f"{jrc.get('degradation_ha',0):,.4f}"],
        ["JRC",      "Regrowth acumulado",        f"{jrc.get('regrowth_ha',0):,.4f}"],
        ["FIRMS",    "Incendios activos",          f"{firms.get('fire_area_ha',0):,.4f}"],
        ["MODIS",    "Área quemada",              f"{modis.get('burn_area_ha',0):,.4f}"],
        ["Hansen",   "% área afectada",           f"{pct:.2f}%"],
    ], [1.3*inch, 2.7*inch, 2*inch]))
    story.append(Spacer(1, 0.2*inch))

    # ── 2. Gráficas de barras ─────────────────────────────────────────
    story.append(Paragraph("2. Pérdida anual por dataset", heading_style))
    story.append(Spacer(1, 0.1*inch))

    bar_configs = [
        ("Hansen — pérdida forestal",     hansen.get("by_year", []),         "Hansen"),
        ("JRC — deforestación anual",     jrc.get("by_year_defor", []),      "JRC Defor"),
        ("JRC — degradación anual",       jrc.get("by_year_degrad", []),     "JRC Degrad"),
        ("JRC — regrowth anual",          jrc.get("by_year_regrowth", []),   "Regrowth"),
        ("FIRMS — incendios anuales",     firms.get("by_year", []),          "FIRMS"),
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

    # ── 5. Comparativa incendios ──────────────────────────────────────
    fire_datasets = {
        "FIRMS": rows_to_dict(firms.get("by_year", [])),
        "MODIS": rows_to_dict(modis.get("by_year", [])),
    }
    make_comparative_section(
        story, heading_style,
        "5. Comparativa anual — incendios y área quemada",
        fire_datasets, "Promedio Fuego"
    )

    # ── 6. Geometría ─────────────────────────────────────────────────
    story.append(Paragraph("6. Geometría del polígono (WKT)", heading_style))
    story.append(Paragraph(
        f"<font size=7>{polygon_wkt[:600]}...</font>", styles["Normal"]))

    doc.build(story)
    buffer.seek(0)
    return buffer


def generate_excel(polygon_area_ha, hansen, glad, jrc, firms=None, modis=None):
    firms = firms or {}
    modis = modis or {}
    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        # Resumen
        pd.DataFrame([{
            "Área polígono (ha)":     polygon_area_ha,
            "Hansen pérdida (ha)":    hansen.get("total_loss_ha", 0),
            "Hansen ganancia (ha)":   hansen.get("gain_ha", 0),
            "GLAD alertas (ha)":      glad.get("alert_area_ha", 0),
            "JRC deforestación (ha)": jrc.get("deforestation_ha", 0),
            "JRC degradación (ha)":   jrc.get("degradation_ha", 0),
            "JRC regrowth (ha)":      jrc.get("regrowth_ha", 0),
            "FIRMS incendios (ha)":   firms.get("fire_area_ha", 0),
            "MODIS quemado (ha)":     modis.get("burn_area_ha", 0),
            "% área afectada":        round(hansen.get("total_loss_ha", 0) /
                                            polygon_area_ha * 100, 2)
                                      if polygon_area_ha > 0 else 0,
        }]).to_excel(writer, sheet_name="Resumen", index=False)

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

        # Comparativa incendios
        fire_ds = {
            "FIRMS": rows_to_dict(firms.get("by_year", [])),
            "MODIS": rows_to_dict(modis.get("by_year", [])),
        }
        fire_ds = {k: v for k, v in fire_ds.items() if v}
        all_years_f = sorted(set(y for d in fire_ds.values() for y in d.keys()))
        if all_years_f:
            rows = []
            for y in all_years_f:
                row = {"Año": y}
                vals = []
                for ds in fire_ds:
                    v = fire_ds[ds].get(y, 0)
                    row[ds] = v
                    vals.append(v)
                row["Promedio Fuego"] = round(sum(vals) / len(vals), 4)
                rows.append(row)
            cols = ["Año"] + list(fire_ds.keys()) + ["Promedio Fuego"]
            pd.DataFrame(rows)[cols].to_excel(
                writer, sheet_name="Comparativa incendios", index=False)

        # Hojas individuales
        for sheet_name, rows in [
            ("Hansen anual",     hansen.get("by_year", [])),
            ("JRC defor anual",  jrc.get("by_year_defor", [])),
            ("JRC degrad anual", jrc.get("by_year_degrad", [])),
            ("JRC regrowth",     jrc.get("by_year_regrowth", [])),
            ("FIRMS anual",      firms.get("by_year", [])),
            ("MODIS anual",      modis.get("by_year", [])),
        ]:
            if rows:
                df = pd.DataFrame(rows)
                df.columns = ["Año", "Área (ha)"]
                df.to_excel(writer, sheet_name=sheet_name, index=False)

    buffer.seek(0)
    return buffer