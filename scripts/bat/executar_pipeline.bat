@echo off
:: =============================================================================
:: executar_pipeline.bat
:: Orquestrador da rotina de ETL de Originacao de Credito via Task Scheduler.
:: Garante execucao unica por dia (flag de sucesso) e loga tudo em arquivo.
:: =============================================================================

chcp 65001 > nul

:: --- Configuracao (ajuste conforme o ambiente) ------------------------------
set "DIRETORIO_RAIZ=C:\Ambiente_ETL\Projetos\Originacao_Credito"
set "DIRETORIO_LOGS=%DIRETORIO_RAIZ%\logs"
set "SCRIPT_PYTHON=%DIRETORIO_RAIZ%\pipeline_originacao_credito.py"
set "EXECUTAVEL_PYTHON=C:\Python39\python.exe"

set "DATA_HOJE=%date:~-4%-%date:~3,2%-%date:~0,2%"
set "ARQUIVO_LOG=%DIRETORIO_LOGS%\etl_originacao_%DATA_HOJE%.log"
set "FLAG_SUCESSO=%DIRETORIO_LOGS%\SUCESSO_%DATA_HOJE%.flag"

if not exist "%DIRETORIO_LOGS%" mkdir "%DIRETORIO_LOGS%"

call :log "Iniciando orquestrador (%DATA_HOJE% %time%)"

:: --- Evita reprocessar se a carga do dia ja foi concluida -------------------
if exist "%FLAG_SUCESSO%" (
    call :log "Carga de %DATA_HOJE% ja concluida. Encerrando sem reprocessar."
    exit /b 0
)

:: --- Validacao do script de origem -------------------------------------------
if not exist "%SCRIPT_PYTHON%" (
    call :log "ERRO: script Python nao encontrado em %SCRIPT_PYTHON%"
    exit /b 1
)

:: --- Execucao do pipeline -----------------------------------------------------
cd /d "%DIRETORIO_RAIZ%"
call :log "Executando pipeline: %SCRIPT_PYTHON%"

"%EXECUTAVEL_PYTHON%" "%SCRIPT_PYTHON%" >> "%ARQUIVO_LOG%" 2>&1
set "CODIGO_RETORNO=%errorlevel%"

:: --- Tratamento do resultado ---------------------------------------------------
if %CODIGO_RETORNO% equ 0 (
    type nul > "%FLAG_SUCESSO%"
    call :log "SUCESSO: Rotina finalizada sem erros. Flag gerada."
    exit /b 0
) else (
    call :log "ERRO: Rotina retornou codigo %CODIGO_RETORNO%."
    exit /b %CODIGO_RETORNO%
)

:: --- Funcao auxiliar de log -----------------------------------------------------
:log
echo [%date% %time%] %~1 >> "%ARQUIVO_LOG%" 2>&1
exit /b 0