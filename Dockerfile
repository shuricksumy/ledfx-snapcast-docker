# Step 1: Builder Stage
FROM debian:bookworm-slim AS builder

# Install necessary packages
# Install necessary packages
# RUN apt-get update && apt-get upgrade -y && apt-get install -y \
#     build-essential \
#     cmake \
#     python3
# RUN apt-get install -y \
#     libasound2-dev \
#     libpulse-dev \
#     libvorbisidec-dev \
#     libvorbis-dev \
#     libopus-dev \
#     libflac-dev \
#     libsoxr-dev \
#     alsa-utils \
#     libavahi-client-dev \
#     avahi-daemon \
#     libexpat1-dev \
#     libatlas3-base \
#     portaudio19-dev \
#     pulseaudio \
#     gcc \
#     git \
#     python3-pip \
#     python3-venv \
#     avahi-daemon \
#     libboost-system-dev \
#     libboost-thread-dev \
#     libboost-program-options-dev \
#     libboost-test-dev \
#     nodejs \
#     npm \
#     python3-numpy

RUN apt-get update && apt-get upgrade -y && apt-get install -y \
    nodejs \
    npm \
    python3-numpy \
    pkg-config \
    build-essential \
    cmake \
    python3-pip \
    python3-venv

# ## Clone Snapcast repository from the master branch
# WORKDIR /src
# RUN git clone --branch master https://github.com/badaix/snapcast.git

# ## Build Snapcast
# WORKDIR /src/snapcast
# RUN mkdir build && cd build && \
#     cmake .. -DBOOST_ROOT=/usr/include/boost -DBUILD_CLIENT=ON -DBUILD_SERVER=ON -DBUILD_WITH_PULSE=OFF && \
#     cmake --build .

# Binaries are located in /src/snapcast/bin (we will copy them in the next steps)
# <snapcast dir>/bin/snapclient
# <snapcast dir>/bin/snapserver

# ## Clone Snapweb repository from the master branch
# WORKDIR /src
# RUN git clone --branch master https://github.com/badaix/snapweb.git
# ## Build Snapcast
# WORKDIR /src/snapweb
# RUN npm install &&\
#     npm install --save-dev -g typescript &&\
#     make
# ## <snapweb dir>dist

# Set the working directory
WORKDIR /ledfx

# Create a Python virtual environment
RUN python3 -m venv /ledfx/venv

# Activate the virtual environment and install ledfx
RUN /ledfx/venv/bin/python -m pip install --upgrade pip wheel setuptools
RUN /ledfx/venv/bin/pip install sounddevice
#RUN /ledfx/venv/bin/python -m pip install ledfx
RUN /ledfx/venv/bin/python -m pip install git+https://github.com/LedFx/LedFx.git

FROM debian:bookworm-slim

RUN apt-get update && apt-get upgrade -y && apt-get install -y \
    alsa-utils \
    dbus-daemon \
    avahi-daemon \
    libavahi-common-dev \
    libavahi-client3 \
    libavahi-client-dev \
    libvorbis-dev \
    libvorbisidec1 \
    libflac12 \
    libopus0 \
    libsoxr0 \
    libjack0 \
    python3 \
    libportaudio2 \
    libatlas3-base \
    portaudio19-dev  \
    pulseaudio \
    pulseaudio-utils \
    libpulse0 \


# Set environment variables to detect architecture
ARG ARCH
RUN if [ -z "$ARCH" ]; then ARCH=$(dpkg --print-architecture); fi && echo "Architecture: $ARCH"

# Set package paths based on architecture
COPY pkg/snapclient_0.31.0-1_amd64_bookworm.deb             /tmp/pkg/snapclient_0.31.0-1_amd64_bookworm.deb
COPY pkg/snapclient_0.31.0-1_arm64_bookworm.deb             /tmp/pkg/snapclient_0.31.0-1_arm64_bookworm.deb
COPY pkg/snapserver_0.31.0-1_amd64_bookworm.deb             /tmp/pkg/snapserver_0.31.0-1_amd64_bookworm.deb
COPY pkg/snapclient_0.31.0-1_amd64_bookworm_with-pulse.deb  /tmp/pkg/snapclient_0.31.0-1_amd64_bookworm_with-pulse.deb
COPY pkg/snapclient_0.31.0-1_arm64_bookworm_with-pulse.deb  /tmp/pkg/snapclient_0.31.0-1_arm64_bookworm_with-pulse.deb
COPY pkg/snapserver_0.31.0-1_arm64_bookworm.deb             /tmp/pkg/snapserver_0.31.0-1_arm64_bookworm.deb

RUN if [ "$(dpkg --print-architecture)" = "arm64" ]; then \
        apt-get install -y /tmp/pkg/snapclient_0.31.0-1_arm64_bookworm_with-pulse.deb; \
        apt-get install -y /tmp/pkg/snapserver_0.31.0-1_arm64_bookworm.deb; \
    elif [ "$(dpkg --print-architecture)" = "amd64" ]; then \
        apt-get install -y /tmp/pkg/snapclient_0.31.0-1_amd64_bookworm_with-pulse.deb; \
        apt-get install -y /tmp/pkg/snapserver_0.31.0-1_amd64_bookworm.deb; \
    else \
        echo "Unsupported architecture"; exit 1; \
    fi

# Clean up
RUN rm -rf /tmp/pkg


RUN apt-get autoremove -y \
    && apt-get clean -y \
    && rm -rf /var/lib/apt/lists/*
    
#COPY --from=builder /src/snapweb/dist /usr/share/snapserver/snapweb
#COPY --from=builder /src/snapcast/bin/snapserver /usr/bin/snapserver
#COPY --from=builder /src/snapcast/bin/snapclient /usr/bin/snapclient
COPY --from=builder /ledfx/venv /ledfx/venv

ENV PYTHONUNBUFFERED=1

WORKDIR /
RUN mkdir /config
COPY snapserver.conf /etc/snapserver.conf
COPY startup.sh startup.sh
COPY startup.py startup.py
RUN chmod +x /startup.sh
RUN chmod +x /startup.py
EXPOSE 1704 1705 1780 8888
# ENTRYPOINT [ "/startup.sh" ]
ENTRYPOINT ["python3",  "-u", "/startup.py"]


