@echo off
REM ============================================================================
REM entrenar.bat — entrenamiento COMPLETO y reutilizable, SOLO muestras MANUALES
REM (sin INEGI): muestreo (sample -> samples.parquet) -> entrenar -> versiona.
REM
REM Pasa cualquier argumento de train.py. Ejemplo (modelo oficial actual):
REM   entrenar.bat --drop-class 11 --rodrigo-drop 1 2 4 5 7 --groups groups_v2.csv ^
REM       --features-like entrenamientos\entrenamiento_04\rf_model.pkl --version manual_b3_v3
REM   (--rodrigo-drop 1 2 4 5 7 = excluye bosque/selva/pastizal/aguacate/otro-perenne de Rodrigo
REM    por etiquetado inconsistente; conserva su agave y demás clases validadas.)
REM
REM Re-muestrea desde los tiles + labels_merged.gpkg ACTUALES (usa los features.tif
REM de out/). REQUIERE F: conectada. Si el muestreo falla, ABORTA (para no entrenar
REM con una tabla vieja). Para solo probar otros args del modelo SIN re-muestrear:
REM   run_producer.bat train.py --table samples.parquet --version X ...
REM ============================================================================
echo ========== 1/2: muestreo (predictores bajo labels_merged) ==========
call "%~dp0run_producer.bat" sample.py --max-per-poly 400
if errorlevel 1 (
  echo.
  echo ERROR en sample.py ^(^?F: desconectada^?^) -- ABORTO para no entrenar con tabla vieja.
  exit /b 1
)

echo ========== 2/2: entrenar RandomForest ^(solo manual^) ==========
call "%~dp0run_producer.bat" train.py --table samples.parquet %*

echo.
echo LISTO. Resultados en rf_report.md (y en entrenamientos\^<version^>\ si pasaste --version).
