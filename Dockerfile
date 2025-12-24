# ==========================================
# STEP 1: BUILDER STAGE
# ==========================================
FROM debian:trixie-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-venv \
    python3-numpy \
    build-essential \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /ledfx

# Create Virtual Environment and install LedFx
RUN python3 -m venv /ledfx/venv
RUN /ledfx/venv/bin/pip install --no-cache-dir --upgrade pip wheel setuptools && \
    /ledfx/venv/bin/pip install --no-cache-dir sounddevice ledfx

# ==========================================
# STEP 2: FINAL STAGE
# ==========================================
FROM debian:trixie-slim

# Install system dependencies for Trixie
# Note: libflac12 is the correct package name for Trixie stable
RUN apt-get update && apt-get install -y --no-install-recommends \
    alsa-utils \
    dbus-daemon \
    avahi-daemon \
    libavahi-client3 \
    libvorbisidec1 \
    libflac12 \
    libopus0 \
    libsoxr0 \
    libportaudio2 \
    pulseaudio \
    pulseaudio-utils \
    python3 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Handle Manual Snapcast Installation
# This uses the built-in TARGETARCH (amd64 or arm64)
ARG TARGETARCH
COPY pkg/snapclient_*_${TARGETARCH}_*pipwire.deb /tmp/snapclient.deb
COPY pkg/snapserver_*_${TARGETARCH}_*pipwire.deb /tmp/snapserver.deb

# Install the local .deb files and fix any potential dependency gaps
RUN apt-get update && \
    apt-get install -y /tmp/snapclient.deb /tmp/snapserver.deb || apt-get install -y -f && \
    rm /tmp/*.deb && \
    rm -rf /var/lib/apt/lists/*

# Copy the Python environment from the builder
COPY --from=builder /ledfx/venv /ledfx/venv

# Setup Environment
ENV PATH="/ledfx/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

WORKDIR /
RUN mkdir /config

# Ensure these files exist in your local build directory
COPY snapserver.conf /etc/snapserver.conf
COPY startup.py startup.py
RUN chmod +x /startup.py

# Ports:
# 1704: Snapcast Stream | 1705: Control | 1780: Web UI | 8888: LedFx UI
EXPOSE 1704 1705 1780 8888

ENTRYPOINT ["python3", "-u", "/startup.py"]
