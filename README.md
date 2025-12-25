# Docker Builder for Snapcast and LedFX

A high-performance, multi-arch (AMD64/ARM64) Docker image based on Debian 13 (Trixie). Optimized for low-latency audio, discovery via Avahi/mDNS, and flexible audio backends (ALSA/PipeWire).

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
| DEVICE_NAME     | ALSA device name hint (matched via aplay -L)              | -           |
| PLAYER_OPTIONS  | Specific Snapclient backend options (e.g., device=hw:1,0) | -           |
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
    privileged: true 
    network_mode: host
    volumes:
      - ${DATA_DIR}/snapserver/config:/config
      - /tmp/snapfifo:/tmp/snapfifo
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
      - HOST=192.168.111.111
      - SOUND_BACKEND=alsa
      - DEVICE_NAME=DX5
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
      - SOUND_BACKEND=alsa
      - PLAYER_OPTIONS=device=hw:Loopback,0,0
```
---

## 🎷 Case 4: PipeWire Integration (Client Mode)

For hosts running PipeWire natively (Ubuntu 22.04+, Fedora, etc.). This maps the host's audio socket directly into the container.

Using PipeWire with this Docker container allows the audio stream to appear as a native application on your host system.

1. Install
```
# Update your package list
sudo apt update

# Install the recommended PipeWire metapackage for audio
# This automatically includes wireplumber (session manager) and 
# compatibility layers for ALSA and PulseAudio applications.
sudo apt install pipewire-audio wireplumber

# Enable the services for your user (do NOT use sudo for these)
systemctl --user --now enable pipewire pipewire-pulse wireplumber
```

2. Prerequisites (Host Machine):
   - Verify PipeWire is running: ``` systemctl --user status pipewire.service ```
   - Identify your User ID: id -u (usually 1000)
   - Run ```pactl info | grep "Server Name"```

3. Docker Compose Configuration:
   To link the container, mount the socket and set the environment.

```
services:
  snapclient-pw:
    image: ghcr.io/shuricksumy/ledfx-snapcast-docker:latest
    container_name: snapclient_pipewire
    user: "1000:1000" 
    environment:
      - ROLE=client
      - HOST=192.168.111.111
      - SOUND_BACKEND=pipewire
      - XDG_RUNTIME_DIR=/run/user/1000
    volumes:
      - /run/user/1000/pipewire-0:/run/user/1000/pipewire-0
    network_mode: host
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