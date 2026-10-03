@echo off
REM ============================================================================
REM finish_05.bat — completa la temporalidad (32 tiles costeros, lectura secuencial)
REM y entrena entrenamiento_05. Correr en Command Prompt (NO en segundo plano):
REM     finish_05.bat
REM Tarda ~7-8 h (los costeros van secuenciales para no congelar PC). Es RESUMIBLE:
REM si se corta, vuelve a correrlo y salta lo ya hecho.
REM ============================================================================
set TILES=r001c006 r001c012 r001c014 r001c015 r002c004 r002c005 r002c006 r002c007 r002c009 r002c010 r002c011 r002c012 r002c014 r002c015 r002c016 r003c005 r003c006 r003c007 r003c008 r003c009 r003c010 r003c011 r003c012 r003c013 r003c014 r003c015 r004c002 r006c000 r006c007 r006c010 r006c011 r007c002

echo ========== 1/5: generar 32 costeros (secuencial, ~7h, resumible) ==========
call "%~dp0run_producer.bat" s2_export.py --states 14 --tile-ids %TILES%

echo ========== 2/5: reintento de rezagados (timeouts) ==========
call "%~dp0run_producer.bat" s2_export.py --states 14 --tile-ids %TILES%

echo ========== 3/5: muestreo (47 bandas + DEM) ==========
call "%~dp0run_producer.bat" sample.py --max-per-poly 400

echo ========== 4/5: negativos INEGI ==========
call "%~dp0run_producer.bat" add_inegi_negatives.py

echo ========== 5/5: entrenar entrenamiento_05 (agrupado + DEM + temporalidad) ==========
call "%~dp0run_producer.bat" train.py --groups groups.csv --rodrigo-drop 5 7

echo.
echo ============================================================================
echo  LISTO. Revisa rf_report.md (es el entrenamiento_05). Avisale a Claude para
echo  guardar la version y comparar matorral/bosque contra el 04.
echo ============================================================================
