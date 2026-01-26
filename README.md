# Docker Builder for Snapcast, Squeezelite, and LedFX

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
| **EXTRA_ARGS** | Raw flags passed to the primary binary of the role | - |

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
    volumes:
      - ./ledfx_config:/root/.ledfx
```

## 📦 Case 2: Standalone Snapserver
Starts Snapserver and creates named pipes (/tmp/snapfifo and /tmp/snapfifo_ledfx) for external audio ingestion.

```YAML
services:
  snapserver:
    image: ghcr.io/shuricksumy/ledfx-snapcast-docker:latest
    container_name: snapcast_audio
    restart: always
    network_mode: host
    environment:
      - ROLE=snapserver
    volumes:
      - ${DATA_DIR}/snapserver/config:/config
      - /tmp/snapfifo:/tmp
```

## 🔈 Case 3: Hardware Player (ALSA / Direct DAC)
Recommended for Audiophile playback. Bypasses software mixers to talk directly to your hardware. Use aplay -L to find your device string.

```YAML
services:
  dx5_player:
    image: ghcr.io/shuricksumy/ledfx-snapcast-docker:latest
    container_name: snapclient_dx5
    restart: unless-stopped
    devices:
      - "/dev/snd:/dev/snd"
    environment:
      - ROLE=snapclient
      - SNAP_HOST=192.168.111.111
      - SNAP_CLIENT_ID=LivingRoom-DX5
      - ALSA_DEVICE=plughw:DX5
```