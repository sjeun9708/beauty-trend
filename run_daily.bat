@echo off
REM 작업 스케줄러가 매일 이 파일을 실행해요. 결과 기록은 run.log 에 쌓여요.
chcp 65001 >nul
set PYTHONUTF8=1
cd /d %~dp0
echo ===== %date% %time% ===== >> run.log
python main.py >> run.log 2>&1
