FROM debian:trixie-slim AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip python3-venv python3-dev python3-numpy \
    build-essential pkg-config cmake git \
    libasound2-dev libjack-dev portaudio19-dev libportaudio2 libsamplerate0-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /ledfx
RUN python3 -m venv /ledfx/venv
RUN /ledfx/venv/bin/pip install --no-cache-dir --upgrade pip wheel setuptools
RUN /ledfx/venv/bin/pip install --no-cache-dir ledfx

FROM debian:trixie-slim
# Added pulseaudio and libasound2-plugins
RUN apt-get update && apt-get install -y --no-install-recommends \
    alsa-utils libasound2-plugins pulseaudio-utils pulseaudio \
    dbus-daemon avahi-daemon \
    libvorbis-dev libflac-dev libopus0 libsoxr0 \
    libasound2-dev libjack-dev portaudio19-dev libportaudio2 libsamplerate0-dev \
    squeezelite python3 && apt-get clean && rm -rf /var/lib/apt/lists/*

ARG TARGETARCH
COPY pkg/snapclient_*_${TARGETARCH}_*_with-pulse.deb /tmp/snapclient.deb
COPY pkg/snapserver_*_${TARGETARCH}_*.deb /tmp/snapserver.deb
RUN apt-get update && apt-get install -y /tmp/snapclient.deb /tmp/snapserver.deb || apt-get install -y -f \
    && rm /tmp/*.deb && rm -rf /var/lib/apt/lists/*

COPY --from=builder /ledfx/venv /ledfx/venv
ENV PATH="/ledfx/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

WORKDIR /
RUN mkdir -p /config
COPY snapserver.conf /etc/snapserver.conf
COPY startup.py startup.py
RUN chmod +x /startup.py

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD find /tmp/supervisor_health -mmin -0.5 || exit 1

ENTRYPOINT ["python3", "-u", "/startup.py"]