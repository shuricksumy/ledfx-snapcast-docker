
# Docker builder for [Snapcast](https://github.com/badaix/snapcast) and [LedFX](https://github.com/LedFx/LedFx)

---

## ✅ Supported Roles

- `server`: Runs Snapserver  
- `client`: Runs Snapclient  
- `ledfx_client`: Runs Snapclient + LedFx  
- `ledfx`: Runs only LedFx  

---

## 🔧 Environment Variables

| Variable         | Description                                                |
|------------------|------------------------------------------------------------|
| `ROLE`           | `server`, `client`, `ledfx`, or `ledfx_client`             |
| `HOST`           | IP/hostname of Snapserver                                  |
| `SOUND_BACKEND`  | `alsa`, `pulse`, or `loopback`                             |
| `DEVICE_NAME`    | ALSA device name (matched using `aplay -L`)               |
| `CLIENT_ID`      | Optional name for Snapclient instance                      |
| `EXTRA_ARGS`     | Additional parameters passed to snapclient                 |
| `LOOPBACK_INDEX` | Required if `SOUND_BACKEND=loopback` (e.g., `10`)          |


---

## 🔊 Snapclient with ALSA

```yaml
version: '3.9'

services:
  snapclient:
    image: ghcr.io/shuricksumy/snapcast:latest
    container_name: snapclient
    restart: unless-stopped
    devices:
      - "/dev/snd:/dev/snd"
    environment:
      - UID=1000
      - GID=1000
      - ROLE=client
      - HOST=192.168.88.111
      - SOUND_BACKEND=alsa
      - DEVICE_NAME=DX3 Pro
      - CLIENT_ID=DX3 Pro
      - EXTRA_ARGS=--sampleformat 48000:24:*
    volumes:
      - /dev/snd:/dev/snd
    labels:
      - "com.centurylinklabs.watchtower.enable=true"
```

---

## 🎛 Snapclient + LedFx (Loopback)

```yaml
version: '3.9'

services:
  snapclient-ledfx:
    image: ghcr.io/shuricksumy/snapcast:latest
    container_name: snapclient-ledfx
    restart: unless-stopped
    ports:
      - "8888:8888"
    devices:
      - "/dev/snd:/dev/snd"
    environment:
      - ROLE=ledfx_client
      - HOST=192.168.88.111
      - SOUND_BACKEND=loopback
      - LOOPBACK_INDEX=10
      - CLIENT_ID=LedFX
      - EXTRA_ARGS=--sampleformat 48000:24:*
    volumes:
      - $DATA_DIR/ledfx:/root/.ledfx
    labels:
      - "com.centurylinklabs.watchtower.enable=true"
```

---

## 🌈 LedFx Only

```yaml
version: '3.9'

services:
  ledfx:
    image: ghcr.io/shuricksumy/snapcast:latest
    container_name: ledfx
    restart: unless-stopped
    ports:
      - "8889:8888"
    devices:
      - "/dev/snd:/dev/snd"
    environment:
      - ROLE=ledfx
    volumes:
      - $DATA_DIR/ledfx:/root/.ledfx
    labels:
      - "com.centurylinklabs.watchtower.enable=true"
```

---

## 📡 Snapserver

```yaml
version: '3.9'

services:
  snapserver:
    image: ghcr.io/shuricksumy/snapcast:latest
    container_name: snapserver
    restart: unless-stopped
    environment:
      - ROLE=server
    volumes:
      - ${DATA_DIR}/snapcast:/tmp/snapcast
      - ${DATA_DIR}/snapserver/config:/config
    network_mode: host
    labels:
      - "com.centurylinklabs.watchtower.enable=true"
```

---

## 🎶 LedFx + Squeezelite with Loopback

```yaml
version: '3.9'

services:
  ledfx:
    image: ghcr.io/shuricksumy/snapcast:latest
    container_name: ledfx
    restart: unless-stopped
    ports:
      - "8888:8888"
    devices:
      - "/dev/snd:/dev/snd"
    depends_on:
      - squeezelite-ledfx
    environment:
      - ROLE=ledfx
      - SOUND_BACKEND=loopback
      - LOOPBACK_INDEX=10
    volumes:
      - $DATA_DIR/ledfx:/root/.ledfx
    labels:
      - "com.centurylinklabs.watchtower.enable=true"

  squeezelite-ledfx:
    image: giof71/squeezelite
    container_name: squeezelite-ledfx
    devices:
      - /dev/snd:/dev/snd
    network_mode: host
    environment:
      - SQUEEZELITE_NAME=LedFx
      - SQUEEZELITE_AUDIO_DEVICE=hw:CARD=Loopback,DEV=0
      - SQUEEZELITE_SERVER_PORT=192.168.88.111:3483
      - STARTUP_DELAY_SEC=0
    restart: unless-stopped
    labels:
      - "com.centurylinklabs.watchtower.enable=true"
```

---

## ✅ Tips

- For `loopback` backend, ensure kernel module `snd-aloop` is loaded and `LOOPBACK_INDEX` matches index.
- Use `aplay -L` to find and verify available ALSA devices.
- In LedFx settings, select `Loopback` as audio input device.

## 🧠 Loopback Device Setup

To use the loopback audio device with Snapclient + LedFx or Squeezelite:

1. Create the config file: `sudo nano /etc/modprobe.d/loopback.conf`:

```bash
# sudo nano /etc/modprobe.d/loopback.conf
options snd-aloop index=10
# options snd-aloop enable=1,1 index=10,11
```

2. Create the file: `sudo nano /etc/modules-load.d/ledfx.conf`:

```bash
# sudo nano /etc/modules-load.d/ledfx.conf
snd-aloop
```

3. Load the module (or reboot):

```bash
sudo modprobe -r snd-aloop
sudo modprobe snd-aloop
```

4. Confirm it’s loaded:

```bash
aplay -L | grep -A 1 Loopback
```