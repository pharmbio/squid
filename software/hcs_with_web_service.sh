#!/bin/bash
cd ~/squid/software
UV_PROJECT_ENVIRONMENT="$HOME/.venvs/squid" PYTHONUNBUFFERED=x squid_web_service=0.0.0.0:5050 uv run python main_hcs.py 2>&1 | tee "log-$(date --iso-8601=seconds).stdio.txt"
