# Step 1: Builder Stage
FROM alpine:latest AS builder

# Install necessary packages
# Install necessary packages
RUN apk update && apk add --no-cache \
    alpine-sdk \
    alsa-lib-dev \
    avahi-dev \
    boost-dev \
    build-base \
    cmake \
    curl \
    expat-dev \
    flac-dev \
    gcc \
    git \
    libffi-dev \
    libvorbis-dev \
    musl-dev \
    npm \
    opus-dev \
    pulseaudio-dev \
    py3-pip \
    py3-virtualenv \
    python3 \
    python3-dev \
    soxr-dev 

# Clone Snapcast repository from the master branch
WORKDIR /src
RUN git clone --branch master https://github.com/badaix/snapcast.git

# Build Snapcast
WORKDIR /src/snapcast
RUN mkdir build && cd build && \
    cmake .. -DBOOST_ROOT=/usr/include/boost -DBUILD_CLIENT=ON -DBUILD_SERVER=ON -DBUILD_WITH_PULSE=OFF && \
    cmake --build .

# Binaries are located in /src/snapcast/bin (we will copy them in the next steps)
# <snapcast dir>/bin/snapclient
# <snapcast dir>/bin/snapserver

# Clone Snapweb repository from the master branch
WORKDIR /src
RUN git clone --branch master https://github.com/badaix/snapweb.git
# Build Snapcast
WORKDIR /src/snapweb
RUN npm install &&\
    npm install --save-dev -g typescript &&\
    make
# <snapweb dir>dist

# Set the working directory
WORKDIR /ledfx

# Create a Python virtual environment
RUN python3 -m venv /ledfx/venv

# Activate the virtual environment and install ledfx
RUN . /ledfx/venv/bin/activate && pip install --upgrade pip setuptools 
RUN . /ledfx/venv/bin/activate && pip install ledfx numpy sounddevice

FROM alpine:latest

RUN apk add --no-cache musl \
   python3 \
   dbus \
   avahi \
   avahi-compat-libdns_sd \
   alsa-lib \
   libgcc \
   mpv \
   portaudio 

RUN rm -rf /var/cache/apk/* 
    
COPY --from=builder /src/snapweb/dist /usr/share/snapserver/snapweb
COPY --from=builder /src/snapcast/bin/snapserver /usr/bin/snapserver
COPY --from=builder /src/snapcast/bin/snapclient /usr/bin/snapclient
COPY --from=builder /ledfx/venv /ledfx/venv

WORKDIR /
RUN mkdir /config
COPY snapserver.conf /etc/snapserver.conf
COPY startup.sh startup.sh
RUN chmod +x /startup.sh
EXPOSE 1704 1705 1780 8888
ENTRYPOINT [ "/startup.sh" ]


