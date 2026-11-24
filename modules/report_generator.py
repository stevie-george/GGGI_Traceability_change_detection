import io
import struct
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, Image
from reportlab.lib.units import inch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator, FuncFormatter
from datetime import datetime

from modules.gee_analysis import LULC_CLASSES, LULC_PALETTE

# color (#hex) por class_id, desde la paleta oficial
_COLOR_OF = {cid: "#" + col for (cid, _), col in zip(LULC_CLASSES, LULC_PALETTE)}
def color_of(cid):
    return _COLOR_OF.get(cid, "#888888")

ACCENT = colors.HexColor("#1a5276")

# Estilo "científico" común para las figuras matplotlib (fondo blanco, grid tenue)
SCI_RC = {
    "font.family": "DejaVu Sans", "font.size": 9,
    "axes.titlesize": 10, "axes.titleweight": "bold", "axes.titlecolor": "#1a5276",
    "axes.edgecolor": "#444444", "axes.linewidth": 0.8,
    "axes.grid": True, "grid.color": "#e8e8e8", "grid.linewidth": 0.7,
    "axes.axisbelow": True, "xtick.color": "#333", "ytick.color": "#333",
    "axes.labelcolor": "#333", "text.color": "#222",
    "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 7.5,
}

def _apply_sci():
    plt.rcParams.update(SCI_RC)

def _savebuf(fig, dpi=180):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig); buf.seek(0)
    return buf

def _png_size(data):
    w, h = struct.unpack(">II", data[16:24])     # IHDR
    return w, h

def _img(buf_or_bytes, width):
    """reportlab Image escalada a `width` conservando proporción."""
    data = buf_or_bytes.getvalue() if hasattr(buf_or_bytes, "getvalue") else buf_or_bytes
    w, h = _png_size(data)
    return Image(io.BytesIO(data), width=width, height=width * h / w)


def rows_to_dict(rows, yr_key="year", area_key="area_ha"):
    return {r[yr_key]: r[area_key] for r in rows} if rows else {}

def styled_table(data_rows, col_widths, header=True):
    t = Table(data_rows, colWidths=col_widths)
    style = [
        ("GRID",           (0, 0), (-1, -1), 0.4, colors.HexColor("#c9c9c9")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef4fa")]),
        ("FONTSIZE",       (0, 0), (-1, -1), 8),
        ("PADDING",        (0, 0), (-1, -1), 4),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                  ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
                  ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold")]
    t.setStyle(TableStyle(style))
    return t


# ─────────────────────────────── Figuras ────────────────────────────────────
def fig_class_bars(lulc_rows, defor_rows, exclude_ids):
    """Figura 1: a) cobertura por clase, b) deforestación por clase (barras con
    color de clase; /// = excluida de la neta)."""
    _apply_sci()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 3.9))

    def hbar(ax, rows, title, xlabel, hatch=False):
        rows = sorted([r for r in rows if r.get("area_ha", 0) > 0], key=lambda r: r["area_ha"])
        if not rows:
            ax.text(0.5, 0.5, "Sin datos", ha="center", va="center", color="#999",
                    transform=ax.transAxes); ax.set_title(title, loc="left"); return
        names = [r["name"] for r in rows]; vals = [r["area_ha"] for r in rows]
        cols = [color_of(r["class_id"]) for r in rows]
        bars = ax.barh(names, vals, color=cols, edgecolor="#333", linewidth=0.5)
        if hatch:
            for b, r in zip(bars, rows):
                if r["class_id"] in exclude_ids:
                    b.set_hatch("///"); b.set_alpha(0.55)
        vmax = max(vals)
        for b, v in zip(bars, vals):
            ax.text(b.get_width() + vmax * 0.01, b.get_y() + b.get_height() / 2,
                    f"{v:,.1f}", va="center", fontsize=7, color="#222")
        ax.set_title(title, loc="left"); ax.set_xlabel(xlabel); ax.set_xlim(0, vmax * 1.16)
        # Menos ticks + separador de miles -> no se amontonan con valores grandes
        dec = 0 if vmax >= 50 else 1
        ax.xaxis.set_major_locator(MaxNLocator(nbins=5))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p, d=dec: f"{v:,.{d}f}"))
        ax.tick_params(axis="x", labelsize=7.5)
        for s in ("top", "right"): ax.spines[s].set_visible(False)
        ax.tick_params(length=0)

    hbar(ax1, lulc_rows, "a) Cobertura del suelo por clase", "Área (ha)")
    hbar(ax2, defor_rows, "b) Deforestación por clase de cobertura", "Pérdida forestal (ha)", hatch=True)
    ax2.text(0.98, 0.02, "/// = excluida (agrícola/urbano)", transform=ax2.transAxes,
             ha="right", va="bottom", fontsize=6.6, color="#666", style="italic")
    fig.suptitle("Figura 1. Cobertura y deforestación por clase (LULC RF v6)",
                 x=0.01, ha="left", fontsize=11, fontweight="bold", color="#1a5276")
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    return _savebuf(fig)


def fig_timeseries(defor_lines, fire_by_year):
    """Figura 2: a) pérdida/regeneración por año (líneas), b) área quemada (barras)."""
    _apply_sci()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 3.6))
    allyears = sorted(set(y for d, _ in defor_lines.values() for y in d))
    if allyears:
        for name, (d, color) in defor_lines.items():
            ax1.plot(allyears, [d.get(y, 0) for y in allyears], marker="o", ms=4,
                     lw=1.8, label=name, color=color)
        ax1.legend(frameon=False, loc="upper left")
        ax1.set_xticks(allyears)
        for lbl in ax1.get_xticklabels(): lbl.set_rotation(45); lbl.set_ha("right")
    else:
        ax1.text(0.5, 0.5, "Sin datos anuales", ha="center", va="center",
                 color="#999", transform=ax1.transAxes)
    ax1.set_title("a) Pérdida y regeneración por año", loc="left")
    ax1.set_xlabel("Año"); ax1.set_ylabel("Área (ha)")

    fyears = sorted(fire_by_year)
    if fyears:
        ax2.bar([str(y) for y in fyears], [fire_by_year[y] for y in fyears],
                color="#e74c3c", alpha=0.85, edgecolor="#922")
        for lbl in ax2.get_xticklabels(): lbl.set_rotation(45); lbl.set_ha("right")
    else:
        ax2.text(0.5, 0.5, "Sin incendios", ha="center", va="center",
                 color="#999", transform=ax2.transAxes)
    ax2.set_title("b) Área quemada por año (MODIS)", loc="left")
    ax2.set_xlabel("Año"); ax2.set_ylabel("Área (ha)")
    for ax in (ax1, ax2):
        for s in ("top", "right"): ax.spines[s].set_visible(False)
    fig.suptitle("Figura 2. Dinámica temporal de pérdida, regeneración e incendios",
                 x=0.01, ha="left", fontsize=11, fontweight="bold", color="#1a5276")
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    return _savebuf(fig)


def build_narrative(area, hansen, defor_lulc, modis=None):
    modis = modis or {}
    loss = hansen.get("total_loss_ha", 0) or 0
    pct = (loss / area * 100) if area else 0
    parts = [f"En el polígono analizado ({area:,.1f} ha) se detectaron {loss:,.1f} ha "
             f"de pérdida de cobertura forestal (Hansen), equivalentes al {pct:.2f}% del área."]
    by = [c for c in defor_lulc.get("by_class", []) if c.get("area_ha", 0) > 0]
    total_cls = defor_lulc.get("total_ha", 0) or 0
    net = defor_lulc.get("net_ha")
    if by and total_cls:
        top = max(by, key=lambda c: c["area_ha"])
        parts.append(f"La mayor parte de la pérdida ({top['area_ha'] / total_cls * 100:.0f}%) "
                     f"ocurrió sobre la clase <b>{top['name']}</b>.")
    if net is not None and defor_lulc.get("by_class"):
        excl = ", ".join(defor_lulc.get("exclude_names", []))
        parts.append(f"La deforestación neta —excluyendo clases agrícolas y urbanas "
                     f"({excl})— fue de <b>{net:,.1f} ha</b>.")
    byears = hansen.get("by_year", [])
    if byears:
        peak = max(byears, key=lambda r: r["area_ha"])
        parts.append(f"El año con mayor pérdida fue {peak['year']} ({peak['area_ha']:,.1f} ha).")
    burn = modis.get("burn_area_ha", 0) or 0
    if burn > 0:
        parts.append(f"Se registraron {burn:,.1f} ha de área quemada (MODIS) en el período.")
    return " ".join(parts)


# ─────────────────────────────── PDF ────────────────────────────────────────
def generate_pdf(polygon_area_ha, hansen, glad, jrc, polygon_wkt,
                 modis=None, lulc=None, defor_lulc=None, meta=None, map_png=None):
    modis = modis or {}; lulc = lulc or {}; defor_lulc = defor_lulc or {}; meta = meta or {}
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=0.7 * inch,
                            leftMargin=0.7 * inch, topMargin=0.7 * inch, bottomMargin=0.7 * inch)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("tt", parent=styles["Title"], fontSize=16, textColor=ACCENT, spaceAfter=2)
    sub_style   = ParagraphStyle("sub", parent=styles["Normal"], fontSize=11, textColor=colors.HexColor("#555"))
    heading     = ParagraphStyle("hh", parent=styles["Heading2"], fontSize=12, textColor=ACCENT)
    body        = ParagraphStyle("body", parent=styles["Normal"], fontSize=9.5, leading=13)
    cap         = ParagraphStyle("cap", parent=styles["Normal"], fontSize=7.5, textColor=colors.HexColor("#777"))
    story = []

    # ── Encabezado + metadatos ───────────────────────────────────────
    story.append(Paragraph("Sistema de Consenso en Pérdida de Cobertura", title_style))
    story.append(Paragraph(f"Análisis: <b>{meta.get('name') or '(sin nombre)'}</b>", sub_style))
    story.append(Spacer(1, 0.12 * inch))
    centroid = meta.get("centroid")
    loc = f"{centroid[0]:.4f}, {centroid[1]:.4f}" if centroid else "—"
    sources = ", ".join(meta.get("sources", [])) or "—"
    meta_tbl = [
        ["Fecha", datetime.now().strftime("%d/%m/%Y %H:%M"), "Área", f"{polygon_area_ha:,.2f} ha"],
        ["Período", meta.get("period", "—"), "Ubicación (centro)", loc],
        ["Modelo LULC", meta.get("model", "RF v6"), "Fuentes", sources],
    ]
    t = Table(meta_tbl, colWidths=[1.1 * inch, 2.2 * inch, 1.5 * inch, 2.2 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef4fa")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#eef4fa")),
        ("FONTNAME",   (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME",   (2, 0), (2, -1), "Helvetica-Bold"),
        ("TEXTCOLOR",  (0, 0), (0, -1), ACCENT), ("TEXTCOLOR", (2, 0), (2, -1), ACCENT),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9c9c9")),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.18 * inch))

    # ── 1. Resumen ejecutivo ─────────────────────────────────────────
    story.append(Paragraph("1. Resumen ejecutivo", heading))
    story.append(Paragraph(build_narrative(polygon_area_ha, hansen, defor_lulc, modis), body))
    story.append(Spacer(1, 0.1 * inch))
    pct = round(hansen.get("total_loss_ha", 0) / polygon_area_ha * 100, 2) if polygon_area_ha else 0
    sr = [
        ["Fuente", "Indicador", "Área (ha)"],
        ["Polígono", "Área total",             f"{polygon_area_ha:,.2f}"],
        ["Hansen",   "Pérdida forestal",        f"{hansen.get('total_loss_ha',0):,.4f}"],
        ["Hansen",   "Ganancia forestal",       f"{hansen.get('gain_ha',0):,.4f}"],
        ["GLAD",     "Alertas deforestación",   f"{glad.get('alert_area_ha',0):,.4f}"],
        ["JRC",      "Deforestación acumulada", f"{jrc.get('deforestation_ha',0):,.4f}"],
        ["JRC",      "Degradación acumulada",   f"{jrc.get('degradation_ha',0):,.4f}"],
        ["MODIS",    "Área quemada",            f"{modis.get('burn_area_ha',0):,.4f}"],
    ]
    if defor_lulc.get("by_class"):
        sr.append(["Hansen×LULC", "Deforestación neta (excl. agrícola/urbano)",
                   f"{defor_lulc.get('net_ha',0):,.4f}"])
    sr.append(["Hansen", "% área afectada", f"{pct:.2f}%"])
    story.append(styled_table(sr, [1.3 * inch, 3.1 * inch, 1.6 * inch]))
    story.append(Spacer(1, 0.18 * inch))

    # ── 2. Mapa del análisis ─────────────────────────────────────────
    if map_png:
        story.append(Paragraph("2. Mapa del análisis", heading))
        story.append(_img(map_png, 6.9 * inch))
        story.append(Paragraph(
            "Figura. a) Clasificación LULC; b) deforestación por año (Hansen) sobre satélite; "
            "c) deforestación (rojo) superpuesta sobre la cobertura. Contorno cian = polígono.", cap))
        story.append(Spacer(1, 0.18 * inch))

    # ── 3. Cobertura y deforestación por clase ───────────────────────
    lulc_rows  = [c for c in lulc.get("by_class", []) if c.get("area_ha", 0) > 0]
    defor_rows = [c for c in defor_lulc.get("by_class", []) if c.get("area_ha", 0) > 0]
    if lulc_rows or defor_rows:
        story.append(Paragraph("3. Cobertura y deforestación por clase", heading))
        story.append(_img(fig_class_bars(lulc_rows, defor_rows,
                                          defor_lulc.get("exclude_ids", [])), 6.9 * inch))
        if defor_rows:
            story.append(Paragraph(
                f"Deforestación total clasificada <b>{defor_lulc.get('total_ha',0):,.2f} ha</b> · "
                f"excluida agrícola/urbano {defor_lulc.get('excluded_ha',0):,.2f} ha · "
                f"neta <b>{defor_lulc.get('net_ha',0):,.2f} ha</b>.", cap))
        story.append(Spacer(1, 0.18 * inch))

    # ── 4. Dinámica temporal ─────────────────────────────────────────
    defor_lines = {
        "Hansen":       (rows_to_dict(hansen.get("by_year", [])),        "#e74c3c"),
        "JRC defor":    (rows_to_dict(jrc.get("by_year_defor", [])),     "#8e44ad"),
        "JRC regrowth": (rows_to_dict(jrc.get("by_year_regrowth", [])),  "#27ae60"),
    }
    defor_lines = {k: v for k, v in defor_lines.items() if v[0]}
    fire = rows_to_dict(modis.get("by_year", []))
    if defor_lines or fire:
        story.append(Paragraph("4. Dinámica temporal", heading))
        story.append(_img(fig_timeseries(defor_lines, fire), 6.9 * inch))
        story.append(Spacer(1, 0.18 * inch))

    # ── 5. Tablas de detalle ─────────────────────────────────────────
    if defor_rows:
        story.append(Paragraph("5. Deforestación por clase (detalle)", heading))
        total = defor_lulc.get("total_ha", 0) or 0
        excl_ids = defor_lulc.get("exclude_ids", [])
        tbl = [["Clase", "Deforestación (ha)", "% de la pérdida", "Excluida"]]
        for c in sorted(defor_rows, key=lambda c: -c["area_ha"]):
            tbl.append([c["name"], f"{c['area_ha']:,.4f}",
                        f"{(c['area_ha']/total*100 if total else 0):.1f}%",
                        "sí" if c["class_id"] in excl_ids else "—"])
        story.append(styled_table(tbl, [2.3 * inch, 1.6 * inch, 1.3 * inch, 0.8 * inch]))
        story.append(Spacer(1, 0.15 * inch))
    if lulc_rows:
        story.append(Paragraph("6. Cobertura del suelo por clase (detalle)", heading))
        tbl = [["Clase", "Área (ha)", "% del polígono"]]
        for c in sorted(lulc_rows, key=lambda c: -c["area_ha"]):
            pctc = round(c["area_ha"] / polygon_area_ha * 100, 2) if polygon_area_ha else 0
            tbl.append([c["name"], f"{c['area_ha']:,.4f}", f"{pctc:.2f}%"])
        story.append(styled_table(tbl, [2.7 * inch, 1.8 * inch, 1.5 * inch]))
        story.append(Spacer(1, 0.18 * inch))

    # ── 7. Geometría ─────────────────────────────────────────────────
    story.append(Paragraph("7. Geometría del polígono (WKT)", heading))
    story.append(Paragraph(f"<font size=7>{polygon_wkt[:600]}...</font>", styles["Normal"]))

    doc.build(story)
    buffer.seek(0)
    return buffer


# ─────────────────────────────── Excel ──────────────────────────────────────
def generate_excel(polygon_area_ha, hansen, glad, jrc, modis=None, lulc=None,
                   defor_lulc=None, meta=None):
    modis = modis or {}; lulc = lulc or {}; defor_lulc = defor_lulc or {}; meta = meta or {}
    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        # Resumen ejecutivo (nombre + narrativa + metadatos)
        exec_rows = [["Nombre del análisis", meta.get("name", "—")],
                     ["Fecha", datetime.now().strftime("%d/%m/%Y %H:%M")],
                     ["Período", meta.get("period", "—")],
                     ["Área (ha)", round(polygon_area_ha, 2)],
                     ["Resumen", build_narrative(polygon_area_ha, hansen, defor_lulc, modis)
                      .replace("<b>", "").replace("</b>", "")]]
        pd.DataFrame(exec_rows, columns=["Campo", "Valor"]).to_excel(
            writer, sheet_name="Resumen ejecutivo", index=False)

        resumen = {}
        if meta.get("name"):
            resumen["Nombre del análisis"] = meta["name"]
        resumen.update({
            "Área polígono (ha)":     polygon_area_ha,
            "Hansen pérdida (ha)":    hansen.get("total_loss_ha", 0),
            "Hansen ganancia (ha)":   hansen.get("gain_ha", 0),
            "GLAD alertas (ha)":      glad.get("alert_area_ha", 0),
            "JRC deforestación (ha)": jrc.get("deforestation_ha", 0),
            "JRC degradación (ha)":   jrc.get("degradation_ha", 0),
            "JRC regrowth (ha)":      jrc.get("regrowth_ha", 0),
            "MODIS quemado (ha)":     modis.get("burn_area_ha", 0),
            "% área afectada":        round(hansen.get("total_loss_ha", 0) / polygon_area_ha * 100, 2)
                                      if polygon_area_ha > 0 else 0,
        })
        if lulc.get("by_class"):
            resumen["Aguacate COBIOCOM (ha)"] = lulc.get("aguacate_ha", 0)
            resumen["Agave COBIOCOM (ha)"]    = lulc.get("agave_ha", 0)
        if defor_lulc.get("by_class"):
            resumen["Deforestación clasificada (ha)"]          = defor_lulc.get("total_ha", 0)
            resumen["Deforestación excl. agrícola/urbano (ha)"] = defor_lulc.get("excluded_ha", 0)
            resumen["Deforestación NETA (ha)"]                 = defor_lulc.get("net_ha", 0)
        pd.DataFrame([resumen]).to_excel(writer, sheet_name="Resumen", index=False)

        lulc_rows = [c for c in lulc.get("by_class", []) if c.get("area_ha", 0) > 0]
        if lulc_rows:
            pd.DataFrame([{
                "Clase": c["name"],
                "Área (ha)": round(c["area_ha"], 4),
                "% polígono": round(c["area_ha"] / polygon_area_ha * 100, 2) if polygon_area_ha else 0,
            } for c in lulc_rows]).to_excel(writer, sheet_name="COBIOCOM LULC", index=False)

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
                row = {"Año": y}; vals = []
                for ds in defor_ds:
                    v = defor_ds[ds].get(y, 0); row[ds] = v; vals.append(v)
                row["Promedio Defor"] = round(sum(vals) / len(vals), 4)
                rows.append(row)
            cols = ["Año"] + list(defor_ds.keys()) + ["Promedio Defor"]
            pd.DataFrame(rows)[cols].to_excel(writer, sheet_name="Comparativa deforestación", index=False)

        for sheet_name, rows in [
            ("Hansen anual",     hansen.get("by_year", [])),
            ("JRC defor anual",  jrc.get("by_year_defor", [])),
            ("JRC degrad anual", jrc.get("by_year_degrad", [])),
            ("JRC regrowth",     jrc.get("by_year_regrowth", [])),
            ("MODIS anual",      modis.get("by_year", [])),
        ]:
            if rows:
                df = pd.DataFrame(rows); df.columns = ["Año", "Área (ha)"]
                df.to_excel(writer, sheet_name=sheet_name, index=False)

    buffer.seek(0)
    return buffer
