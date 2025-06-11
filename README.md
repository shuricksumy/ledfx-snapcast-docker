# Docker builder for [Snapcast](https://github.com/badaix/snapcast) and [LedFX](https://github.com/LedFx/LedFx)

# Snapclient

```docker-compose.yaml```
```
version: '3.9'

services:
  snapclient:
    image: your-snapcast-image:latest
    container_name: snapclient
    environment:
      - ROLE=client
      - HOST=192.168.1.100  # Replace with Snapserver IP
      - EXTRA_ARGS=--sound pulse --soundcard alsa_output.pci-0000_00_1b.0.analog-stereo.monitor --hostID FIIO
      - PULSE_SERVER=unix:/run/user/1000/pulse/native
    volumes:
      - $XDG_RUNTIME_DIR/pulse:/run/user/1000/pulse
      - ~/.config/pulse/cookie:/root/.config/pulse/cookie
      - /dev/snd:/dev/snd  # Allow access to ALSA sound devices
    devices:
      - /dev/snd
    network_mode: host
    restart: unless-stopped

    # 🔄 To use ALSA instead of PulseAudio:
    # environment:
    #   - ROLE=client
    #   - HOST=192.168.1.100
    #   - EXTRA_ARGS=--sound alsa --soundcard default --hostID FIIO
    #   Some more comlex config for DAC
    #   - EXTRA_ARGS=--sound alsa --sampleformat 48000:24:* --soundcard plughw:CARD=Pro,DEV=0 --hostID MX3-Pro
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
  ledfx:
    image: your-snapcast-image:latest
    container_name: ledfx
    environment:
      - ROLE=ledfx
      - HOST=192.168.1.100  # Replace with your Snapserver IP
      - EXTRA_ARGS=--sound pulse --soundcard alsa_output.pci-0000_00_1b.0.analog-stereo.monitor --hostID LedFX
      - PULSE_SERVER=unix:/run/user/1000/pulse/native
    volumes:
      - ./ledfx:/root/.ledfx
      - $XDG_RUNTIME_DIR/pulse:/run/user/1000/pulse
      - ~/.config/pulse/cookie:/root/.config/pulse/cookie
      - /dev/snd:/dev/snd
    devices:
      - /dev/snd
    #network_mode: host
    ports:
      - "8889:8888" # ledfx web port
    restart: unless-stopped

    # 🔄 To use ALSA (ensure loopback is enabled):
    # environment:
    #   - ROLE=ledfx
    #   - HOST=192.168.1.100
    #   - EXTRA_ARGS=--sound alsa --soundcard Loopback --hostID LedFX
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
