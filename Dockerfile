# --- Stage 1: Builder ---
FROM debian:trixie-slim AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip python3-venv python3-dev python3-numpy \
    build-essential pkg-config cmake git \
    libasound2-dev libjack-dev portaudio19-dev libportaudio2 libsamplerate0-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /ledfx
RUN python3 -m venv /ledfx/venv
RUN /ledfx/venv/bin/pip install --no-cache-dir --upgrade pip wheel setuptools
RUN /ledfx/venv/bin/pip install --no-cache-dir sounddevice ledfx

# --- Stage 2: Final ---
FROM debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    alsa-utils dbus-daemon avahi-daemon libavahi-client3 \
    libvorbis-dev libflac-dev libopus0 libsoxr0 libportaudio2 \
    pulseaudio pulseaudio-utils python3 \
    libpipewire-0.3-modules pipewire-bin procps \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

ARG TARGETARCH
RUN if [ -z "$TARGETARCH" ]; then TARGETARCH=$(dpkg --print-architecture); fi
COPY pkg/snapclient_*_${TARGETARCH}_*pipewire.deb /tmp/snapclient.deb
COPY pkg/snapserver_*_${TARGETARCH}_*pipewire.deb /tmp/snapserver.deb
RUN apt-get update && (apt-get install -y /tmp/snapclient.deb /tmp/snapserver.deb || apt-get install -y -f) \
    && rm /tmp/*.deb && rm -rf /var/lib/apt/lists/*

COPY --from=builder /ledfx/venv /ledfx/venv
ENV PATH="/ledfx/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PIPEWIRE_MODULE_DIR=/usr/lib/aarch64-linux-gnu/pipewire-0.3
ENV SPA_PLUGIN_DIR=/usr/lib/aarch64-linux-gnu/spa-0.2

WORKDIR /
RUN mkdir /config
COPY snapserver.conf /etc/snapserver.conf
COPY startup.py startup.py
RUN chmod +x /startup.py
EXPOSE 1704 1705 1780 8888
ENTRYPOINT ["python3", "-u", "/startup.py"]