# Docker builder for [Snapcast](https://github.com/badaix/snapcast) and [LedFX](https://github.com/LedFx/LedFx)

# Snapclient

```docker-compose.yaml```
```
version: '3.9'

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
      - DEVICE_NAME=DX3 Pro
      - SOUND_BACKEND=alsa
      - CLIENT_ID=DX3 Pro
      - EXTRA_ARGS=--sampleformat 48000:24:*
    volumes:
      - /dev/snd:/dev/snd
      - $XDG_RUNTIME_DIR/pulse:/run/user/1000/pulse
    networks:
      - default
      - npm_proxy
```

# LedFX
### Need to run ```sudo modprobe snd-aloop``` to add Loopback device

- Add file ```ledfx.conf``` to ```/etc/modules-load.d/``` on host machine
```ledfx.conf```
```
# add loop snd card to use it as input for ledfx
snd-aloop
```
- Reboot host machine or just run ```sudo modprobe snd-aloop```
- Start docker container
- Select device ```Loopback``` in ledfx UI setting. 
- Can be first or second device - just try what is the proper (for me, the second works).
  
![image](https://github.com/user-attachments/assets/23bc92e0-c878-4807-9fa6-0597fbae3fe6)


```docker-compose.yaml```
```
version: '3.9'

services:
    snapclient-ledfx:
      image: ghcr.io/shuricksumy/snapcast:latest
      container_name: snapclient-ledfx
      restart: unless-stopped
      ports:
        - "8889:8888" # ledfx web port
      devices:
        - "/dev/snd:/dev/snd"  # Access to host audio devices
      environment:
        - HOST=192.168.88.111  # Static IP of Snapserver
        - ROLE=ledfx
        - PULSE_SERVER=unix:/run/user/1000/pulse/native
        - SOUND_BACKEND=alsa
        - DEVICE_NAME=Loopback
        - CLIENT_ID=LedFX
        #- EXTRA_ARGS=--sound pulse --hostID LedFX --input-device=default
      volumes:
        - $DATA_DIR/ledfx:/root/.ledfx
        - /run/user/1000/pulse:/run/user/1000/pulse
```

# Snapserver

```docker-compose.yaml```
```
version: '3.9'
services:
  snapserver:
    image: dc8ca81f78b9
    container_name: snapserver
    environment:
      - ROLE=server
    #  - EXTRA_ARGS=
    volumes:
      - ${DATA_DIR}/snapcast:/tmp/snapcast
      - ${DATA_DIR}/snapserver/config:/config
    network_mode: host
    restart: unless-stopped
```
