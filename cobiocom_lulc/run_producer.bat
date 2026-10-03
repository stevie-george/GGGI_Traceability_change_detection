@echo off
setlocal
REM ============================================================================
REM run_producer.bat — run a COBIOCOM pipeline script in the `cobiocom` conda env
REM with a CLEAN, env-only PATH.
REM
REM Why: base Anaconda is on your system PATH, and its older GDAL DLLs shadow the
REM env's GDAL 3.12 -> rasterio fails with "DLL load failed importing _warp".
REM Activating the env doesn't remove base from PATH; this launcher does.
REM
REM Usage (from a normal Command Prompt, from anywhere):
REM     run_producer.bat s2_export.py --out out --states 14 --limit 1
REM     run_producer.bat make_qgis_assets.py
REM     run_producer.bat package_for_consultants.py --name jalisco
REM
REM If you move the env or project, edit ENVDIR / PROJDIR below.
REM ============================================================================
set "ENVDIR=C:\Users\StephaniePatriciaGeo\anaconda3\envs\cobiocom"
set "PROJDIR=C:\Users\StephaniePatriciaGeo\Documents\deforestation_alert\cobiocom_lulc"

set "PATH=%ENVDIR%;%ENVDIR%\Library\bin;%ENVDIR%\Library\usr\bin;%ENVDIR%\Library\mingw-w64\bin;%ENVDIR%\Scripts;%ENVDIR%\bin;%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\Wbem"
set "GDAL_DATA=%ENVDIR%\Library\share\gdal"
set "PROJ_LIB=%ENVDIR%\Library\share\proj"
set "PROJ_DATA=%ENVDIR%\Library\share\proj"

REM Retry a transient blob read ONCE, then abandon a hung/unreachable scene fast
REM (drop it from the median) instead of grinding through retries. The composite
REM fills in from the dozens of scenes that do load, so coverage stays ~97-98%.
set "GDAL_HTTP_MAX_RETRY=1"
set "GDAL_HTTP_RETRY_DELAY=1"
set "GDAL_HTTP_TIMEOUT=30"
set "GDAL_HTTP_CONNECTTIMEOUT=10"

cd /d "%PROJDIR%"
"%ENVDIR%\python.exe" %*
endlocal
