# Monitor Setup

Alice has two external monitors shared between a **Linux desktop** and a **MacBook**. Both computers can claim either monitor independently via DDC/CI.

## Physical layout

```
[ Top monitor:  Samsung S34C65xU ultrawide 3440x1440  ] <- wall-mounted above
[ Main monitor: Samsung LC32G5xT 2560x1440            ] <- desk, centred below
[ MacBook                                               ] <- desk, to the left
```

## Connections

| Monitor | Linux connector | MacBook connector |
|---------|----------------|-------------------|
| Top (S34C65xU) | DisplayPort -> Linux (DRM DP-2, DDC bus 7) | USB-C |
| Main (LC32G5xT) | DisplayPort -> Linux (DRM DP-3, DDC bus 8) | HDMI |

The MacBook has no USB-B upstream connection to either monitor; PBP/PIP split-screen is **OSD-only** and cannot be controlled via software.

## Input codes

| Monitor | Linux (DP) | MacBook | Notes |
|---------|-----------|---------|-------|
| Top (bus 7) | `0x0f` / `15` | `0x36` / `54` (USB-C) | none |
| Main (bus 8) | `0x0f` / `15` | `0x06` / `6` (HDMI) | ddcutil mislabels 0x06 as "Composite video 2", which is correct |

## Tools

- **Linux:** `ddcutil` (DDC/CI over I2C). Alice's user must be in the `i2c` group.
- **macOS:** `m1ddc` (homebrew), `displayplacer` (homebrew) for layout restore.

## Shell aliases (written to `~/.zshrc` by `section_ddcutil()`)

```
top-dp       switch top monitor    -> Linux (DP)
top-usbc     switch top monitor    -> MacBook (USB-C)
top-bright   get top monitor brightness
top-set-bright <0-100>

main-dp      switch main monitor   -> Linux (DP)
main-hdmi    switch main monitor   -> MacBook (HDMI)

mon-status   show current input on both monitors
mon-linux    switch both -> Linux + restore KDE layout (Linux only)
mon-mac      switch both -> MacBook + restore displayplacer layout (macOS only)
mon-discover probe m1ddc display numbers (macOS only; run once)
```

## macOS one-time setup (must be done on the MacBook)

After running `./setup.sh --only ddcutil` on the Mac:

1. **Find display numbers:**
   ```zsh
   mon-discover
   ```
2. **Set the numbers in `~/.zshrc.local`** (create if absent):
   ```zsh
   export MON_MAIN_NUM=<number>   # LC32G5xT (HDMI)
   export MON_TOP_NUM=<number>    # S34C65xU (USB-C)
   ```
3. **Arrange displays as preferred**, then capture the layout:
   ```zsh
   displayplacer list
   ```
4. **Set the layout string in `~/.zshrc.local`:**
   ```zsh
   export MON_MAC_LAYOUT='<paste displayplacer list output here>'
   ```

## Verifying the setup

**Linux:**
```bash
./setup.sh --verify --only ddcutil
ddcutil --bus=7 getvcp 60    # top monitor current input
ddcutil --bus=8 getvcp 60    # main monitor current input
```

**macOS:**
```bash
./setup.sh --verify --only ddcutil
mon-discover                  # confirms m1ddc sees both monitors
mon-status                    # shows current input on each
```

If `mon-linux` or `mon-mac` doesn't restore layout correctly:
- Linux: check `kscreen-doctor` output; re-run with `kscreen-doctor output.DP-2.position.0,0 output.DP-3.position.364,1440`
- macOS: re-run `displayplacer list` with the preferred layout active and update `MON_MAC_LAYOUT`
