"""
plan_sample.py — build the COBIOCOM sampling + labeling calendar (see MASTER_PLAN.md).

Supervised classification only needs a representative SAMPLE of tiles labelled;
the model then classifies every tile. This picks a systematic spatial sample per
state, orders the states, and lays the sample against the team timeline
(Tona full-time = 75%, Mau + Rodrigo only the first HELPER_WEEKS).

    run_producer.bat plan_sample.py            # print the plan (no changes)
    run_producer.bat plan_sample.py --apply    # + stamp the Jalisco sample into
                                               #   tile_grid.gpkg's 'consultant' column

Tune the knobs below (stride, weeks, split, order) and re-run.
"""
import argparse
import re
import datetime as dt
from pathlib import Path

import geopandas as gpd
from s2_export import read_aoi, make_grid

HERE = Path(__file__).resolve().parent
GPKG = HERE / "tile_grid.gpkg"

# ---- knobs -----------------------------------------------------------------
STRIDE      = 2            # sample every STRIDE-th row & col (2 -> ~1-in-4)
MIN_SAMPLE  = 12           # small states below this fall back to all tiles
WK_TOTAL    = 21           # Tona's horizon (~5 months)
HELPER_WEEKS = 8           # Mau + Rodrigo work only this long (~2 months)
TONA_SHARE  = 0.75         # Tona's share of the sample
START       = dt.date(2026, 9, 7)                  # week-1 Monday
ORDER       = ["14", "16", "18", "06", "11", "01", "32", "24"]   # rest-order: edit freely
NAME = {"14": "Jalisco", "16": "Michoacan", "18": "Nayarit", "06": "Colima",
        "11": "Guanajuato", "01": "Aguascalientes", "32": "Zacatecas", "24": "San Luis Potosi"}
DONE = {"r003c005", "r003c006", "r003c007", "r003c008", "r003c009", "r003c010",
        "r003c011", "r003c012", "r003c013", "r003c014",
        "r004c001", "r004c002", "r004c003", "r004c004"}          # 14 delivered pilots
# ----------------------------------------------------------------------------


def rc(t):
    m = re.search(r"r(\d+)c(\d+)", str(t))   # search, no match: tolera prefijo de estado ("16_r000c000")
    return (int(m.group(1)), int(m.group(2)))


def sample(ids):
    """systematic lattice: every STRIDE-th row & col; tiny states -> take all."""
    lat = [t for t in ids if rc(t)[0] % STRIDE == 0 and rc(t)[1] % STRIDE == 0]
    return sorted(lat if len(lat) >= MIN_SAMPLE else ids, key=rc)


def build():
    """-> (state_ids, state_sample, weeks) ; weeks[w] = {who: [(code, tile_id), ...]}"""
    jg = gpd.read_file(GPKG)
    state_ids, state_sample = {}, {}
    for code in ORDER:
        if code == "14":
            ids = sorted(jg.tile_id.tolist(), key=rc)          # Jalisco: ids pelones (grandfathered)
        else:
            ids = sorted([t[0] for t in make_grid(read_aoi([code]), f"{code}_")], key=rc)  # prefijo de estado
        state_ids[code] = ids
        s = sample(ids)
        state_sample[code] = [t for t in s if t not in DONE] if code == "14" else s

    Sr = sum(len(state_sample[c]) for c in ORDER)
    pT = round(TONA_SHARE * Sr / WK_TOTAL)
    pE = round((1 - TONA_SHARE) / 2 * Sr / HELPER_WEEKS)      # each helper

    pool = [(code, t) for code in ORDER for t in state_sample[code]]
    i, weeks = 0, []
    for w in range(1, WK_TOTAL + 1):
        wk = {"tona": [], "mau": [], "rodrigo": []}
        for who, pace in [("tona", pT), ("mau", pE if w <= HELPER_WEEKS else 0),
                          ("rodrigo", pE if w <= HELPER_WEEKS else 0)]:
            take = pool[i:i + pace]
            wk[who] = take
            i += len(take)
        weeks.append(wk)
    return state_ids, state_sample, weeks, Sr, pT, pE, len(pool) - i


def show(state_ids, state_sample, weeks, Sr, pT, pE, leftover):
    print("state             total  sample")
    for c in ORDER:
        print(f"  {NAME[c]:16s} {len(state_ids[c]):5d} {len(state_sample[c]):6d}")
    print(f"  {'TOTAL':16s} {sum(len(state_ids[c]) for c in ORDER):5d} {Sr:6d}")
    print(f"\nTona {pT}/wk x{WK_TOTAL}wk  |  Mau {pE}/wk & Rodrigo {pE}/wk x{HELPER_WEEKS}wk"
          f"  |  leftover {leftover}")
    print("\nwk  Monday      state(s)          tona mau rod  cumul")
    cum = 0
    for w, wk in enumerate(weeks, 1):
        allt = wk["tona"] + wk["mau"] + wk["rodrigo"]
        cum += len(allt)
        st = ",".join(NAME[c][:4] for c in sorted({c for c, _ in allt}, key=ORDER.index)) or "-"
        mon = (START + dt.timedelta(weeks=w - 1)).isoformat()
        print(f"{w:2d}  {mon}  {st:18s}{len(wk['tona']):4d}{len(wk['mau']):4d}"
              f"{len(wk['rodrigo']):4d}  {cum}")


def apply_jalisco(weeks):
    """Stamp the Jalisco sample assignment into tile_grid.gpkg, keeping pilot marks."""
    who_id = {"tona": 1, "mau": 2, "rodrigo": 3}
    assign = {t: who_id[who] for wk in weeks for who in who_id
              for c, t in wk[who] if c == "14"}
    grid = gpd.read_file(GPKG)
    grid["consultant"] = [assign.get(t, cur) for t, cur in
                          zip(grid.tile_id, grid["consultant"])]
    grid.to_file(GPKG, layer="tiles", driver="GPKG")
    n = {v: sum(1 for x in assign.values() if x == v) for v in (1, 2, 3)}
    print(f"\nstamped Jalisco sample into {GPKG.name}: "
          f"tona +{n[1]}, mau +{n[2]}, rodrigo +{n[3]} (pilot marks kept)")


def dump_plan(weeks, path):
    """Exporta el plan completo (los 8 estados) a CSV: una fila por tile muestreado con su
    estado, consultor y semana asignada — listo para descargar por estado más tarde."""
    import csv
    who_id = {"tona": 1, "mau": 2, "rodrigo": 3}
    rows = []
    for w, wk in enumerate(weeks, 1):
        mon = (START + dt.timedelta(weeks=w - 1)).isoformat()
        for who in ("tona", "mau", "rodrigo"):
            for code, tile in wk[who]:
                rows.append([w, mon, code, NAME[code], tile, who, who_id[who]])
    with open(path, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["week", "monday", "state_cve", "state", "tile_id", "consultant", "consultant_id"])
        wr.writerows(rows)
    print(f"\n-> {path.name} ({len(rows)} tiles asignados, 8 estados). "
          f"Para descargar un estado: agrupa por state_cve y pásalo a s2_export --states <cve> --tile-ids ...")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write the Jalisco sample into tile_grid.gpkg's consultant column")
    ap.add_argument("--dump", action="store_true",
                    help="exportar el plan completo de los 8 estados a plan_all_states.csv")
    args = ap.parse_args()
    state_ids, state_sample, weeks, Sr, pT, pE, leftover = build()
    show(state_ids, state_sample, weeks, Sr, pT, pE, leftover)
    if args.apply:
        apply_jalisco(weeks)
    if args.dump:
        dump_plan(weeks, HERE / "plan_all_states.csv")


if __name__ == "__main__":
    main()
