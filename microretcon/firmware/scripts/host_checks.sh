#!/usr/bin/env bash
# POSIX-side CI for the firmware repo — no ESP-IDF needed (DESIGN §9:
# everything above the radio seam is POSIX-first).
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== seam compile-check (host g++, -Werror) =="
g++ -std=c++20 -Wall -Wextra -Werror \
    -I components/micro_pal/esp32/espnow \
    -I components/micro_pal/esp32/sx1262 \
    -I components/micro_usb \
    tests/host/test_seams.cpp -o /tmp/micro_test_seams
/tmp/micro_test_seams
echo "seams OK"

echo "== footprint budget gate =="
bash scripts/footprint_budget.sh
echo "== all green =="