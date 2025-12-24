FROM debian:trixie-slim

# Install system dependencies - Updated for Trixie names
RUN apt-get update && apt-get install -y --no-install-recommends \
    alsa-utils \
    dbus-daemon \
    avahi-daemon \
    libavahi-client3 \
    libvorbisidec1 \
    libflac12t64 \
    libopus0 \
    libsoxr0 \
    libportaudio2 \
    pulseaudio \
    pulseaudio-utils \
    python3 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Handle Manual Snapcast Installation
ARG TARGETARCH
COPY pkg/snapclient_*_${TARGETARCH}_*pipewire.deb /tmp/snapclient.deb
COPY pkg/snapserver_*_${TARGETARCH}_*pipewire.deb /tmp/snapserver.deb

RUN apt-get update && \
    apt-get install -y /tmp/snapclient.deb /tmp/snapserver.deb || apt-get install -y -f && \
    rm /tmp/*.deb && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /ledfx/venv /ledfx/venv
ENV PATH="/ledfx/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

WORKDIR /
RUN mkdir /config
COPY snapserver.conf /etc/snapserver.conf
COPY startup.py startup.py
RUN chmod +x /startup.py

EXPOSE 1704 1705 1780 8888
ENTRYPOINT ["python3", "-u", "/startup.py"]
