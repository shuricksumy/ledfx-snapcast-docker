# Docker builder for [Snapcast](https://github.com/badaix/snapcast) and [LedFX](https://github.com/LedFx/LedFx)

# Snapclient

```
 snapclient:
      image: shuricksumy/snapcast:latest
      container_name: snapclient
      restart: unless-stopped
      devices:
        - "/dev/snd:/dev/snd"  # Access to host audio devices
      environment:
        - HOST=192.168.88.111  # Static IP of Snapserver
        - ROLE=client
        - EXTRA_ARGS=--user snapclient:audio -s BTR3K --hostID FIIO
```

# LedFX
### Need to run ```sudo modprobe snd-aloop``` to add Loopback device

- Add file ```ledfx.conf``` to ```/etc/modules-load.d/``` 
- Reboot host linux
- Select device ```Loopback``` in ledfx UI setting. 
- Can be first or second device - just try what is the proper.
  
![image](https://github.com/user-attachments/assets/23bc92e0-c878-4807-9fa6-0597fbae3fe6)

```ledfx.conf```
```
# add loop snd card to use it as input for ledfx
snd-aloop
```

```
services:
  snapclient-ledfx:
    image: shuricksumy/snapcast:latest
    container_name: snapclient-ledfx
    restart: unless-stopped
    ports:
      - "8888:8888" # ledfx web port
    environment:
      - HOST=192.168.88.111  # Static IP of Snapserver
      - ROLE=ledfx
    volumes:
      - ./ledfx:/root/.ledfx
    devices:
      - "/dev/snd:/dev/snd"  # Access to host audio devices
```

# Snapserver

```
    snapserver:
      image: shuricksumy/snapcast:latest
      container_name: snapserver
      restart: unless-stopped
      network_mode: host
      environment:
        - ROLE=server
      volumes:
        - ${DATA_DIR}/snapcast:/tmp/snapcast
```
