#!/usr/bin/env bash
# Build the MicroRETCON RAK4631 transport-node UF2 into the RETCON
# artifacts tree (what the image's flashing UI serves and the dashboard
# publishes). Paths resolve from this script's location.
set -euo pipefail

RDIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$RDIR/../../.." && pwd)"           # microretcon/firmware/rak -> RETCON root
OUTDIR="$REPO/artifacts/firmware/microretcon"
VER="${MICRORETCON_VER:-r1}"

PIO="${PIO:-pio}"
command -v "$PIO" >/dev/null || PIO="/tmp/resolve312/bin/pio"

echo "== building rak4631_micro =="
(cd "$RDIR" && "$PIO" run -e rak4631_micro)

echo "== hex -> uf2 (nRF52 family, softdevice s140 layout) =="
UF2CONV="$(dirname "$(find ~/.platformio/packages/framework-arduinoadafruitnrf52 -name uf2conv.py 2>/dev/null | head -1)")/uf2conv.py"
[ -n "$UF2CONV" ] || { echo "uf2conv.py not found under ~/.platformio"; exit 1; }

mkdir -p "$OUTDIR"
python3 "$UF2CONV" "$RDIR/.pio/build/rak4631_micro/firmware.hex" \
    -c -f NRF52 -o "$OUTDIR/microretcon-rak4631-$VER.uf2" 2>/dev/null

echo "== artifact:"
ls -la "$OUTDIR"
echo "flash: copy the .uf2 onto the RAK4631's mass-storage drive (double-tap reset to mount it)"
