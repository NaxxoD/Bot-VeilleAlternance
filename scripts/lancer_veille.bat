@echo off
rem Lanceur de la veille, utilisé par la tâche planifiée Windows.
rem Le journal de chaque exécution est ajouté à data\veille.log,
rem puis une pop-up Windows résume le résultat (ou signale un échec).
cd /d "%~dp0.."
set PYTHONIOENCODING=utf-8
echo ===== %date% %time% ===== >> "data\veille.log"
".venv\Scripts\python.exe" -m veille_alternance >> "data\veille.log" 2>&1
set CODE=%ERRORLEVEL%
powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "scripts\notifier.ps1" %CODE%
exit /b %CODE%
