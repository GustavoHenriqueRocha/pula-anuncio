@echo off
rem Dois cliques: pede permissao de administrador e remove o agente.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File ""%~dp0desinstalar-windows.ps1""'"
