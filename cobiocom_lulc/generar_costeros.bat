@echo off
REM ============================================================================
REM generar_costeros.bat — genera (4 temporadas, lectura SECUENCIAL) los 32 tiles
REM costeros de Jalisco que se congelaban con lectura concurrente. One-time / resumible.
REM Correr en Command Prompt; tarda ~7-8 h. Si se corta, vuelve a correrlo (salta hechos).
REM ============================================================================
set TILES=r001c006 r001c012 r001c014 r001c015 r002c004 r002c005 r002c006 r002c007 r002c009 r002c010 r002c011 r002c012 r002c014 r002c015 r002c016 r003c005 r003c006 r003c007 r003c008 r003c009 r003c010 r003c011 r003c012 r003c013 r003c014 r003c015 r004c002 r006c000 r006c007 r006c010 r006c011 r007c002

echo ========== generando 32 costeros (secuencial) ==========
call "%~dp0run_producer.bat" s2_export.py --states 14 --tile-ids %TILES%
echo ========== reintento de rezagados ==========
call "%~dp0run_producer.bat" s2_export.py --states 14 --tile-ids %TILES%
echo.
echo LISTO (o casi — si quedan timeouts, vuelve a correr este .bat).
