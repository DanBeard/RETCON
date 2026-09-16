# retcon_pi — rpi-image-gen v2 build assets

This directory contains everything `rpi-image-gen` (v2.x) needs to build the
RETCON Raspberry Pi image:

```text
retcon_pi/
|-- bdebstrap/            # (reserved) build-time hook scripts run by the runner
|-- config/
|   `-- retcon.yaml       # build entrypoint: device, image and layer selection
`-- layer/
    |-- retcon-suite.yaml # top level layer: base OS + networking + our apps
    `-- retcon-apps.yaml  # copies the repo into the image, builds venv/apps,
                          # polkit/sudo/authbind/dnsmasq/udev setup, crontab
```

## How it fits together

`build_retcon.sh` checks out a pinned `rpi-image-gen` release into
`~/.retcon-build/` and runs:

```bash
rpi-image-gen build -S <repo>/retcon_pi -c retcon.yaml -B ~/.retcon-build/work
```

* `config/retcon.yaml` selects the device layer (`rpizero2w`), the image
  layout (`image-rpios`, MBR + vfat boot + ext4 root), image sizing/naming,
  and the custom `retcon-suite` layer.
* `retcon-suite` pulls in Debian Trixie (arm64 multi-arch base), the
  Raspberry Pi apt repo, essential/rpi utils, **NetworkManager + iwd**
  (RETCON drives wifi over dbus, so systemd-networkd is *not* used),
  wireless regulatory data, ssh, timesync and locales.
* `retcon-apps` does the RETCON-specific work inside the chroot: it copies
  this repository into `/home/retcon/retcon`, runs
  `install_retcon_locally.sh` (python venv, RNS stack, meshchat, node/tls
  proxy), sets up authbind/sudo/polkit/dnsmasq/udev and installs the
  `@reboot` crontab that starts RETCON at boot.

Layers are resolved by name from rpi-image-gen's in-tree library plus this
directory, so layer names referenced in `retcon-suite.yaml` must match the
pinned rpi-image-gen release.

## Device class

The config currently targets `rpizero2w` (Pi Zero 2 W). To target other
boards change `device.layer` in `config/retcon.yaml` to e.g. `pi3`, `pi4`
or `pi5` (see the `device/` directory in the rpi-image-gen checkout).

## Tuning

Image partition sizes and compression are set in the `image:` section of
`config/retcon.yaml`. The runtime RETCON behaviour (mode, wifi, plugins)
is **not** set here — that lives in `retcon_profiles/` and is baked into
the image by copying a profile to `retcon_profiles/active` before running
`build_retcon.sh`.