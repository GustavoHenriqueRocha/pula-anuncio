@echo off
rem Dois cliques: pede permissao de administrador e instala o agente.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File ""%~dp0instalar-windows.ps1""'"
