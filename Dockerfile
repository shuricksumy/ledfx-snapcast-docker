# Step 1: Builder Stage
FROM alpine:latest AS builder

# Install necessary packages
RUN apk add --no-cache \
    build-base \
    cmake \
    alsa-lib-dev \
    pulseaudio-dev \
    libvorbis-dev \
    opus-dev \
    flac-dev \
    soxr-dev \
    avahi-dev \
    expat-dev \
    boost-dev \
    git \
    npm \
    curl \
    alpine-sdk  

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

FROM alpine:latest

RUN apk add --no-cache musl \
   dbus \
   avahi \
   avahi-compat-libdns_sd \
   alsa-lib \
   libgcc \
   mpv

RUN rm -rf /var/cache/apk/*

COPY --from=builder /src/snapweb/dist /usr/share/snapserver/snapweb
COPY --from=builder /src/snapcast/bin/snapserver /usr/bin/snapserver
COPY --from=builder /src/snapcast/bin/snapclient /usr/bin/snapclient

WORKDIR /
COPY snapserver.conf /etc/snapserver.conf
COPY startup.sh startup.sh
RUN chmod +x /startup.sh
# EXPOSE 1704 1705 1780
ENTRYPOINT [ "/startup.sh" ]


