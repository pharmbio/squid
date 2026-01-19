#!/bin/bash
cd ~/squid/software
PYTHONUNBUFFERED=x squid_web_service=0.0.0.0:5050 python3 main_hcs.py 2>&1 | tee "log-$(date --iso-8601=seconds).stdio.txt"
