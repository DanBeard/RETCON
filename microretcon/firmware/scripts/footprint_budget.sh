#!/usr/bin/env bash
# Footprint budget gate — MicroRETCON (DESIGN §9).
#
# Mirrors crns's tests/test_config_profiles.cpp contract at the FIRMWARE
# level: node()/router() + USB + lwIP measured against
# footprint_budget_bytes at build time — regression = red build.
#
# Mechanism (M2 fills the numbers): after `idf.py build`, read the
# .elf/.map section sizes (freertos task stacks + crns node static +
# lwIP + TinyUSB) and compare against budgets table below. Until the
# real link map exists, the script exits 0 with a loud note (scaffold
# state) so CI stays green while stubs only.
#
# Usage: scripts/footprint_budget.sh [path/to/project.map]

set -euo pipefail

MAP="${1:-}"
if [[ -z "$MAP" ]]; then
    echo "footprint: scaffold state — no link map yet, gate passes vacuously"
    exit 0
fi

# Budgets (bytes). Pinned in the M2 brief with their rationale before the
# first real measurement; afterwards only tightened, never loosened.
declare -A BUDGET=(
    # [component]=bytes
)

fail=0
for comp in "${!BUDGET[@]}"; do
    echo "footprint: $comp budget ${BUDGET[$comp]} — measurement lands with M2"
done

# M2: parse the map, per-section sums, compare, exit 1 on regression.
exit $fail