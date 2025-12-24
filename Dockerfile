# --- Stage 1: Build the Python Environment ---
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
# Install LedFx inside the virtual environment
RUN /ledfx/venv/bin/pip install --no-cache-dir --upgrade pip wheel setuptools && \
    /ledfx/venv/bin/pip install --no-cache-dir sounddevice ledfx

# --- Stage 2: Final Image ---
FROM debian:trixie-slim

# Install system dependencies
# Note: Using libflac12t64 for Trixie compatibility
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

# Handle Architecture-specific Snapcast .debs
ARG TARGETARCH
# If building manually without buildx, TARGETARCH might be empty. 
# This line ensures it defaults to amd64 if not specified.
RUN if [ -z "$TARGETARCH" ]; then TARGETARCH=$(dpkg --print-architecture); fi

COPY pkg/snapclient_*_${TARGETARCH}_*pipewire.deb /tmp/snapclient.deb
COPY pkg/snapserver_*_${TARGETARCH}_*pipewire.deb /tmp/snapserver.deb

# Install the .debs and fix any dependency issues automatically
RUN apt-get update && \
    (apt-get install -y /tmp/snapclient.deb /tmp/snapserver.deb || apt-get install -y -f) && \
    rm /tmp/*.deb && \
    rm -rf /var/lib/apt/lists/*

# IMPORTANT: This matches the "AS builder" name from Stage 1
COPY --from=builder /ledfx/venv /ledfx/venv

# Setup Environment
ENV PATH="/ledfx/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

WORKDIR /
RUN mkdir /config
COPY snapserver.conf /etc/snapserver.conf
COPY startup.py startup.py
RUN chmod +x /startup.py

EXPOSE 1704 1705 1780 8888
ENTRYPOINT ["python3", "-u", "/startup.py"]
