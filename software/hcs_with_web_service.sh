#!/bin/bash
export squid_web_service=10.10.0.95:5050
cd /home/pharmbio/Downloads/squid/software
python3 main_hcs.py 2>&1 | tee "log-$(date --iso-8601=seconds).stdio.txt" 
sleep 10

