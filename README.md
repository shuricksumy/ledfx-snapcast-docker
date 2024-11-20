# Docker builder for [Snapcast](https://github.com/badaix/snapcast) and [LedFX](https://github.com/LedFx/LedFx)

# Snapclient

```docker-compose.yaml```
```
 snapclient:
      image: shuricksumy/snapcast:latest
      container_name: snapclient
      restart: unless-stopped
      deploy:
        restart_policy:
          condition: on-failure
          delay: 5s
          max_attempts: 0
      devices:
        - "/dev/snd:/dev/snd"  # Access to host audio devices
      environment:
        - HOST=192.168.88.111  # Static IP of Snapserver
        - ROLE=client
        # BT3K is sound card name
        - EXTRA_ARGS=-s BTR3K --hostID FIIO
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
services:
  snapclient-ledfx:
    image: shuricksumy/snapcast:latest
    container_name: snapclient-ledfx
    restart: unless-stopped
    deploy:
        restart_policy:
          condition: on-failure
          delay: 5s
          max_attempts: 0
    ports:
      - "8888:8888" # ledfx web port
    environment:
      - HOST=192.168.88.111  # Static IP of Snapserver
      - ROLE=ledfx
      # Default EXTRA_ARGS is set as
      # - EXTRA_ARGS=--sound alsa --soundcard "Loopback" --hostID LedFX
    volumes:
      - ./ledfx:/root/.ledfx
    devices:
      - "/dev/snd:/dev/snd"  # Access to host audio devices
```

# Snapserver

```docker-compose.yaml```
```
    snapserver:
      image: shuricksumy/snapcast:latest
      container_name: snapserver
      restart: unless-stopped
      deploy:
        restart_policy:
          condition: on-failure
          delay: 5s
          max_attempts: 0
      network_mode: host
      environment:
        - ROLE=server
      volumes:
        - ${DATA_DIR}/snapcast:/tmp/snapcast
        - ./config:/config
```
