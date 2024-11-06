# Docker builder for [Snapcast](https://github.com/badaix/snapcast)

# snapclient

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

# ledfx + snapclient

```
services:
  snapclient:
    image: test:latest
    container_name: snapclient
    restart: unless-stopped
    ports:
      - "8888:8888" # ledfx web port
    environment:
      - HOST=192.168.88.111  # Static IP of Snapserver
      - ROLE=client-ledfx
      - EXTRA_ARGS=--user snapclient:audio -s BTR3K --hostID FIIO
    volumes:
      - ./ledfx:/root/.ledfx
    devices:
      - "/dev/snd:/dev/snd"  # Access to host audio devices
```

# snapserver

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
