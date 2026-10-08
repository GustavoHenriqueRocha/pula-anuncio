@echo off
rem Inicia o agente do Pula Anuncio sem janela. Para iniciar com o Windows,
rem coloque um atalho deste arquivo em shell:startup (Win+R -> shell:startup).
cd /d "%~dp0"
start "" pythonw agente.py
