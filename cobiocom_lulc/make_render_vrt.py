"""
make_render_vrt.py — mosaicos VRT de los renders de TODOS los tiles construidos,
para ver Jalisco completo en QGIS como capa de contexto.

Un VRT por tipo de render (referencia los .tif en out/, no copia datos):
    mosaics/jalisco_green_TRUE.vrt   color natural, temporada verde (post-lluvias)
    mosaics/jalisco_dry_SWIR.vrt     SWIR secas (mejor para aguacate/agave/cultivo)
    ... etc.

    run_producer.bat make_render_vrt.py                     # set por defecto
    run_producer.bat make_render_vrt.py --renders green_TRUE dry_SWIR
    run_producer.bat make_render_vrt.py --overviews         # + pirámides (display fluido)

Los VRT usan rutas absolutas -> abren directo en QGIS en esta máquina.
"""
import argparse
from pathlib import Path
from osgeo import gdal

gdal.UseExceptions()
HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
MOSAICS = HERE / "mosaics"
DEFAULT = ["green_TRUE", "dry_TRUE", "green_SWIR", "dry_SWIR", "green_CIR", "dry_CIR", "dNDVI"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--renders", nargs="*", default=DEFAULT)
    ap.add_argument("--overviews", action="store_true",
                    help="construir pirámides (.vrt.ovr) para display fluido a escala completa")
    args = ap.parse_args()
    MOSAICS.mkdir(exist_ok=True)

    for r in args.renders:
        files = sorted(str(p) for p in OUT.glob(f"r*c*/*_{r}.tif"))
        if not files:
            print(f"  [omito] {r}: sin archivos"); continue
        vrt = MOSAICS / f"jalisco_{r}.vrt"
        ds = gdal.BuildVRT(str(vrt), files)
        if ds is None:
            print(f"  [error] {r}"); continue
        if args.overviews:
            ds.BuildOverviews("AVERAGE", [2, 4, 8, 16, 32])
        ds = None
        ov = " + pirámides" if args.overviews else ""
        print(f"  {vrt.name}: {len(files)} tiles{ov}")

    print(f"\n-> {MOSAICS}\\   (arrastra jalisco_green_TRUE.vrt al lienzo de QGIS)")


if __name__ == "__main__":
    main()
