#!/bin/bash
export squid_web_service=0.0.0.0:5050
cd ~/squid/software
python3 main_hcs.py 2>&1 | tee "log-$(date --iso-8601=seconds).stdio.txt" 
sleep 10

