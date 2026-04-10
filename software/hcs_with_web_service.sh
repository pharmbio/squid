#!/bin/bash

# Read configuration from squid_c_config.json with web service on 5053:
#   ./hcs_with_web_service.sh squid_c 5053
#
# Default: use conf from machine_config.json with web service on 5050:
#   ./hcs_with_web_service.sh

# put squid name in $1 to load its config, fallback is machine_config.json
export squid_machine_config="${1:-machine_}_config.json"

# web service is at 5050 by default, use $2 to use another port
export squid_web_service="0.0.0.0:${2:-5050}"

# put the venv out of the way so sshfs mounts dont pick it up
export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/squid"

# unbuffer for stdout
export PYTHONUNBUFFERED=x

cd ~/squid/software
uv run python main_hcs.py 2>&1 | tee "log-$(date --iso-8601=seconds).stdio.txt"
