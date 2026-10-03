@echo off
REM ============================================================================
REM entrenar.bat — corre un ENTRENAMIENTO COMPLETO y reutilizable:
REM   muestreo (sample) -> negativos INEGI (add_inegi) -> entrenar (train) -> versiona
REM
REM Pasa cualquier argumento de train.py. Ejemplos:
REM   entrenar.bat --version mi_prueba --groups groups.csv --rodrigo-drop 5 7
REM   entrenar.bat --version base
REM   entrenar.bat --version con_rodrigo --with-rodrigo --groups groups.csv
REM
REM Re-muestrea desde los tiles + etiquetas ACTUALES (usa los features.tif que haya
REM en out/). Si solo quieres probar otros args del modelo SIN re-muestrear, corre
REM train.py directo:  run_producer.bat train.py --version X ...
REM ============================================================================
echo ========== 1/3: muestreo (predictores bajo las etiquetas) ==========
call "%~dp0run_producer.bat" sample.py --max-per-poly 400

echo ========== 2/3: negativos INEGI ==========
call "%~dp0run_producer.bat" add_inegi_negatives.py

echo ========== 3/3: entrenar RandomForest ==========
call "%~dp0run_producer.bat" train.py %*

echo.
echo LISTO. Resultados en rf_report.md  (y en entrenamientos\^<version^>\ si pasaste --version).
