# Docker Builder for Snapcast and LedFX

A high-performance, multi-arch (AMD64/ARM64) Docker image based on Debian 13 (Trixie). Optimized for low-latency audio, discovery via Avahi/mDNS, and flexible audio backends (ALSA).

---

## ✅ Supported Roles

- server: Runs Snapserver (with D-Bus and Avahi for network discovery).
- client: Runs Snapclient (standalone).
- ledfx: Runs LedFx Visualizer + Internal Snapclient (sync mode).

---

## 🔧 Environment Variables

| Variable        | Description                                                 | Default     |
| :-------------- | :---------------------------------------------------------- | :---------- |
| ROLE            | server, client, or ledfx                              | server    |
| HOST            | IP or Hostname of the Snapserver                            | localhost |
| SOUND_BACKEND   | alsa or pipewire                                        | alsa      |
| ALSA_DEVICE     | ALSA device name hint (matched via aplay -L) Ex.hw:Pro, hw:0:0             | -           |
| CLIENT_ID       | Optional unique name for the Snapclient instance            | -           |
| EXTRA_ARGS      | Raw flags passed to the binary (filtered for modern syntax) | -           |

---

## 📡 Case 1: Snapserver (Host Mode)

Uses network_mode: host to allow mDNS/Avahi discovery to reach your entire local network.
```
services:
  snapserver:
    image: ghcr.io/shuricksumy/ledfx-snapcast-docker:latest
    container_name: snapserver
    restart: always
    network_mode: host
    volumes:
      - ${DATA_DIR}/snapserver/config:/config
      - /tmp/snapfifo:/tmp
      - /etc/localtime:/etc/localtime:ro
    environment:
      - ROLE=server
```
---

## 🔊 Case 2: Snapclient (ALSA / Direct DAC)

Recommended for Audiophile playback (e.g., Topping DX5). Bypasses software mixers for direct hardware access.
```
services:
  snapclient:
    image: ghcr.io/shuricksumy/ledfx-snapcast-docker:latest
    container_name: snapclient_dx5
    restart: unless-stopped
    devices:
      - "/dev/snd:/dev/snd"
    environment:
      - ROLE=client
      - HOST=192.168.111.111:1704
      - SOUND_BACKEND=alsa
      - ALSA_DEVICE=hw:DX5
      - CLIENT_ID=LivingRoom-DX5
    networks:
      - default
```
---

## 🌈 Case 3: LedFx + Client (Visualizer)

Starts the LedFx web engine and a hidden Snapclient. The client feeds audio into an ALSA Loopback device which LedFx "listens" to for light synchronization.
```
services:
  ledfx:
    image: ghcr.io/shuricksumy/ledfx-snapcast-docker:latest
    container_name: ledfx_visualizer
    restart: unless-stopped
    privileged: true
    ports:
      - "8888:8888"
    devices:
      - "/dev/snd:/dev/snd"
    environment:
      - ROLE=ledfx
      - HOST=192.168.111.111
      - SOUND_BACKEND=hw:Loopback,10,0
```

---

## 🧠 Setup: ALSA Loopback (Required for LedFx)

Docker cannot load kernel modules. You must load the snd-aloop module on your Host Machine (the physical PC/Pi) before starting the container.

1. Configure for boot:
```
   echo "options snd-aloop index=10" | sudo tee /etc/modprobe.d/loopback.conf
   echo "snd-aloop" | sudo tee /etc/modules-load.d/ledfx.conf
```
2. Load immediately:
```
   sudo modprobe snd-aloop index=10
```
3. Verify presence:
```
   aplay -l | grep Loopback
```
---

## 🛠 Setup: PipeWire on Client Host

If you want to use the pipewire backend:

1. Check UID: Run 'id -u' on your host. If it's not 1000, update the user and XDG_RUNTIME_DIR in the compose file.
2. Socket Path: Ensure the file /run/user/1000/pipewire-0 exists on your host.
3. Permissions: The user inside the container must match the host user to access the socket. Running with user: "1000:1000" handles this.

---

## ✅ Pro Tips
- Process Management: This image uses os.execv to ensure the audio process runs as PID 1, allowing for clean shutdowns.
- D-Bus/Avahi: These are required for Snapcast discovery. If your server isn't appearing in the app, ensure you are using privileged: true and network_mode: host.
- Multi-Arch: This image is natively built for linux/amd64 and linux/arm64.