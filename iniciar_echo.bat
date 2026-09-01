@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

rem Versao "sem console" - o ECHO roda em segundo plano (pythonw), sem janela de
rem terminal nenhuma (mesmo padrao do iniciar_iris.bat/iniciar_argus.bat).
rem Sem interface grafica - so a ponte HTTP (porta 8774, ver echo/api_bridge.py).

start "" /B ".venv\Scripts\pythonw.exe" -m echo.main
