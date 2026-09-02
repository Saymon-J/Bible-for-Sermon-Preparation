@echo off
rem Публикация репозитория на GitHub одной командой.
rem 1) создай ПУСТОЙ репозиторий на github.com (без README и лицензии)
rem 2) запусти:  push-github.bat https://github.com/ИМЯ/РЕПО.git
if "%~1"=="" (
  echo Usage: push-github.bat ^<repository-url^>
  echo Create an empty repo on github.com first ^(no README, no license^).
  exit /b 1
)
git remote remove origin >nul 2>&1
git remote add origin %~1
git push -u origin main
