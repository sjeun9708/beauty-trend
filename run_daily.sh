#!/bin/bash
# 맥/리눅스 cron에 등록하면 매일 자동 실행됩니다.
cd "$(dirname "$0")"
python3 main.py >> run.log 2>&1
