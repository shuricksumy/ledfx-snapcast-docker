# Docker Builder for [Snapcast](https://github.com/snapcast/snapcast), Squeezelite, and [LedFX](https://github.com/LedFx/LedFx)

A high-performance, multi-arch (AMD64/ARM64) Docker image based on Debian 13 (Trixie). This image is uniquely optimized to handle synchronized audio visualization using a headless PulseAudio bridge, eliminating the need for complex ALSA Loopback configurations on the host.

---

## ✅ Supported Roles

* **ledfx-suite**: The "All-in-One" visualizer. Runs PulseAudio, Squeezelite, Snapclient, and LedFx. Audio is routed internally via a virtual Pulse sink.
* **snapserver**: Runs a standalone Snapserver with support for Named Pipes (FIFOs).
* **client**: A dedicated hardware player. Runs Snapclient with direct ALSA access for physical DACs (e.g., Topping DX5).

---

## 🔧 Environment Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| **ROLE** | `ledfx-suite`, `snapserver`, or `snapclient` | `ledfx-suite` |
| **SNAP_HOST** | IP or Hostname of the Snapserver (TCP URI handled automatically) | `127.0.0.1` |
| **SNAP_CLIENT_ID** | Unique name/ID for the Snapclient instance | `LedFx-Node` |
| **ALSA_DEVICE** | Physical device name (Used in `snapclient` role) Ex: `plughw:DX5` | `default` |
| **SNAPCLIENT_LEDFX_ENABLED** | Enable/Disable internal Snapclient in `ledfx-suite` | `true` |
| **SQUEEZELITE_LEDFX_ENABLED** | Enable/Disable internal Squeezelite in `ledfx-suite` | `true` |
| **SQUEEZELITE_NAME** | Name of the player as it appears in LMS | `LedFx` |
| **SQUEEZELITE_MAC** | Fixed MAC address for persistent LMS settings | - |
| **SQUEEZELITE_SERVER_PORT** | Direct `IP:Port` for LMS (skips discovery) | - |
| **SQUEEZELITE_OUTPUT** | PulseAudio sink for Squeezelite (`default` = server default sink) | `default` |
| **FIFO_DIR** | Directory the `snapserver` role creates its named pipes in | `/tmp` |
| **EXTRA_ARGS** | Raw flags passed to the primary binary of the role (`snapserver`, `snapclient`, or `ledfx`) | - |

---

## 🔒 Running unprivileged

The container **runs as UID/GID 1000**, not root. Two things follow from that:

* Bind-mounted directories must be writable by that UID — `chown -R 1000:1000 <dir>` on the host, or override with `user: "<uid>:<gid>"` in compose.
* The LedFx config now lives at **`/home/ledfx/.ledfx`**, not `/root/.ledfx`. If you are upgrading, move the mount and chown the host directory:

```bash
sudo chown -R 1000:1000 ./ledfx_config
# volumes: - ./ledfx_config:/home/ledfx/.ledfx
```

For the `snapclient` role the image user is in the container's `audio` group (gid 29). If `/dev/snd` on your host is owned by a different gid, add it with `group_add`.

---

## ♻️ How the image stays current

Nothing is vendored in this repo. Every build resolves its dependencies fresh:

* **Snapcast** — `snapclient`/`snapserver` `.deb` packages are downloaded from the [upstream release](https://github.com/badaix/snapcast/releases) during the build and verified against the sha256 digest GitHub publishes for each asset. `--build-arg SNAPCAST_VERSION=v0.35.0` pins a specific release; the default `latest` follows upstream.
* **LedFx** — installed from PyPI; `--build-arg LEDFX_VERSION=2.0.x` pins it.
* **Squeezelite** — git submodule; the *Check and Update Submodules* workflow opens a PR when upstream moves.
* **Debian base** — the image is rebuilt every Monday, and a Trivy scan (fixable CRITICAL/HIGH only) publishes to the repository's Security tab.

---

## 📡 Case 1: LedFx Suite (The All-in-One Visualizer)

This role starts a local PulseAudio server and routes both Squeezelite and Snapclient into a virtual "LedFx_Sink". LedFx then "listens" to the monitor of this sink. **No host kernel modules (snd-aloop) required.**

[Image of PulseAudio network streaming architecture]

```yaml
services:
  ledfx_visualizer:
    image: ghcr.io/shuricksumy/ledfx-snapcast-docker:latest
    container_name: ledfx_visualizer
    restart: always
    network_mode: host
    environment:
      - ROLE=ledfx-suite
      - SNAP_HOST=192.168.111.111
      - SQUEEZELITE_NAME=LedFx-Vibe
      - SQUEEZELITE_SERVER_PORT=192.168.111.111:3483
      - SQUEEZELITE_MAC=72:23:90:63:08:66
      # Disable Squeezelite, keep Snapclient active
      - SQUEEZELITE_LEDFX_ENABLED=true
      - SNAPCLIENT_LEDFX_ENABLED=true
    user: "1000:1000"
    security_opt:
      - no-new-privileges:true
    volumes:
      - ./ledfx_config:/home/ledfx/.ledfx
```

## 📦 Case 2: Standalone Snapserver
Starts Snapserver and creates named pipes (`snapfifo` and `snapfifo_ledfx`) for external audio ingestion. They are created in `FIFO_DIR`, which defaults to `/tmp`; point it at a dedicated mounted directory so the host can write to them.

```YAML
services:
  snapserver:
    image: ghcr.io/shuricksumy/ledfx-snapcast-docker:latest
    container_name: snapcast_audio
    restart: always
    network_mode: host
    environment:
      - ROLE=snapserver
      - FIFO_DIR=/fifo
    user: "1000:1000" # chown -R 1000:1000 ${DATA_DIR}/snapserver/config
    volumes:
      - ${DATA_DIR}/snapserver/config:/config
      # Never mount over /tmp itself - the health file and PulseAudio's
      # runtime dirs live there
      - ${DATA_DIR}/snapserver/fifo:/fifo
```

## 🔈 Case 3: Hardware Player (ALSA / Direct DAC)
Recommended for Audiophile playback. Bypasses software mixers to talk directly to your hardware. Use aplay -L to find your device string.

```YAML
services:
  dx5_player:
    image: ghcr.io/shuricksumy/ledfx-snapcast-docker:latest
    container_name: snapclient_dx5
    restart: unless-stopped
    user: "1000:1000"
    devices:
      - "/dev/snd:/dev/snd"
    environment:
      - ROLE=snapclient
      - SNAP_HOST=192.168.111.111
      - SNAP_CLIENT_ID=LivingRoom-DX5
      - ALSA_DEVICE=plughw:DX5
```
