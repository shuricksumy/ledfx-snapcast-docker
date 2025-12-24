# --- Stage 1: Builder ---
FROM debian:trixie-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-venv \
    python3-numpy \
    build-essential \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /ledfx
RUN python3 -m venv /ledfx/venv
RUN /ledfx/venv/bin/pip install --no-cache-dir --upgrade pip wheel setuptools && \
    /ledfx/venv/bin/pip install --no-cache-dir sounddevice ledfx

# --- Stage 2: Final ---
FROM debian:trixie-slim

# Use virtual package names (libflac-dev, libvorbis-dev) 
# instead of specific versioned ones (libflac12t64, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    alsa-utils \
    dbus-daemon \
    avahi-daemon \
    libavahi-client3 \
    libvorbis-dev \
    libflac-dev \
    libopus0 \
    libsoxr0 \
    libportaudio2 \
    pulseaudio \
    pulseaudio-utils \
    python3 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Handle Architecture
ARG TARGETARCH
RUN if [ -z "$TARGETARCH" ]; then TARGETARCH=$(dpkg --print-architecture); fi

# Copy and Install Snapcast
COPY pkg/snapclient_*_${TARGETARCH}_*pipewire.deb /tmp/snapclient.deb
COPY pkg/snapserver_*_${TARGETARCH}_*pipewire.deb /tmp/snapserver.deb

# We use 'apt-get install -y /tmp/...' because it handles dependencies 
# better than 'dpkg -i'. If it fails, the '-f' flag fixes it using the 
# libraries we installed above.
RUN apt-get update && \
    apt-get install -y /tmp/snapclient.deb /tmp/snapserver.deb || apt-get install -y -f && \
    rm /tmp/*.deb && \
    rm -rf /var/lib/apt/lists/*

# Copy Venv from Builder
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
