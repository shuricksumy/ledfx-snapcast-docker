# snapclient

```
 snapclient:
      image: shuricksumy/snapclient:latest
      container_name: snapclient
      restart: always
      devices:
        - "/dev/snd:/dev/snd"  # Access to host audio devices
      environment:
        - HOST=192.168.88.111  # Static IP of Snapserver
        - EXTRA_ARGS=--user snapclient:audio -s BTR3K
```
