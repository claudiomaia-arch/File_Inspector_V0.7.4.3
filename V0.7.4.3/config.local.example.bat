@echo off
REM Copie este arquivo para config.local.bat e preencha os dados reais.
set APP_BASE_URL=http://10.101.0.204:8010
set SMTP_HOST=smtp.seudominio.com
set SMTP_PORT=587
set SMTP_USER=cadinspector@seudominio.com
set SMTP_PASSWORD=troque_esta_senha
set SMTP_FROM=cadinspector@seudominio.com
set SMTP_TLS=true
REM Para teste sem SMTP, descomente:
REM set EMAIL_DEV_MODE=true
