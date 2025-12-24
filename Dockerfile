# --- Stage 1: Builder ---
FROM debian:trixie-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip python3-venv python3-numpy build-essential pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /ledfx
RUN python3 -m venv /ledfx/venv
# Update pip and install LedFx within the venv
RUN /ledfx/venv/bin/pip install --no-cache-dir --upgrade pip wheel setuptools && \
    /ledfx/venv/bin/pip install --no-cache-dir sounddevice ledfx

# --- Stage 2: Final Stage ---
FROM debian:trixie-slim

# Install system dependencies needed for both Snapcast and LedFx
RUN apt-get update && apt-get install -y --no-install-recommends \
    alsa-utils dbus-daemon avahi-daemon libavahi-client3 \
    libvorbisidec1 libflac12t64 libopus0 libsoxr0 \
    libportaudio2 pulseaudio pulseaudio-utils python3 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Use the built-in TARGETARCH to select the correct local .deb file
ARG TARGETARCH

# Copy ONLY the packages relevant to the current architecture to keep layers small
COPY pkg/snapclient_*_${TARGETARCH}_*pipewide.deb /tmp/snapclient.deb
COPY pkg/snapserver_*_${TARGETARCH}_*pipewide.deb /tmp/snapserver.deb

# Install the local .deb files
# 'apt-get install ./*.deb' is better than 'dpkg -i' because it fixes missing dependencies
RUN apt-get update && \
    apt-get install -y /tmp/snapclient.deb /tmp/snapserver.deb && \
    rm /tmp/*.deb && \
    rm -rf /var/lib/apt/lists/*

# Copy the Python environment
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