# --- Stage 0: Fetch Snapcast packages from the upstream GitHub release ---
# Runs on the build host (not under QEMU) - it only downloads, and picks the
# package for $TARGETARCH explicitly.
FROM --platform=$BUILDPLATFORM debian:trixie-slim AS snapcast

ARG TARGETARCH
# Release to install. "latest" resolves the newest published release at build
# time; CI pins the resolved tag so the layer caches between rebuilds.
ARG SNAPCAST_VERSION=latest
ARG SNAPCAST_SUITE=trixie

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl jq \
    && rm -rf /var/lib/apt/lists/*

# Each asset is verified against the sha256 digest the GitHub API reports for
# it, and a missing asset or digest fails the build rather than shipping an
# unverified package.
RUN set -eu; \
    if [ "$SNAPCAST_VERSION" = "latest" ]; then \
        api="https://api.github.com/repos/badaix/snapcast/releases/latest"; \
    else \
        api="https://api.github.com/repos/badaix/snapcast/releases/tags/${SNAPCAST_VERSION}"; \
    fi; \
    curl -fsSL --retry 3 --retry-delay 5 -H "Accept: application/vnd.github+json" "$api" -o /tmp/release.json; \
    tag="$(jq -r .tag_name /tmp/release.json)"; \
    echo "==> Snapcast release ${tag} (${TARGETARCH}/${SNAPCAST_SUITE})"; \
    mkdir -p /debs; \
    for spec in "snapclient:snapclient_.*_${TARGETARCH}_${SNAPCAST_SUITE}_with-pulse[.]deb" \
                "snapserver:snapserver_.*_${TARGETARCH}_${SNAPCAST_SUITE}[.]deb"; do \
        name="${spec%%:*}"; pattern="${spec#*:}"; \
        asset="$(jq -c --arg p "^${pattern}$" '[.assets[] | select(.name | test($p))] | first' /tmp/release.json)"; \
        [ "$asset" != "null" ] || { echo "ERROR: ${tag} has no asset matching ${pattern}" >&2; exit 1; }; \
        url="$(echo "$asset" | jq -r .browser_download_url)"; \
        sha="$(echo "$asset" | jq -r '.digest // ""' | sed 's/^sha256://')"; \
        [ -n "$sha" ] || { echo "ERROR: no sha256 digest published for $(echo "$asset" | jq -r .name)" >&2; exit 1; }; \
        echo "    $(echo "$asset" | jq -r .name)"; \
        curl -fsSL --retry 3 --retry-delay 5 "$url" -o "/debs/${name}.deb"; \
        echo "${sha}  /debs/${name}.deb" | sha256sum -c -; \
    done


# --- Stage 1: Build (LedFx venv + Squeezelite) ---
FROM debian:trixie AS builder

# Changing this busts the apt/pip cache so a scheduled rebuild actually picks
# up new Debian security updates and a new LedFx release (CI sets it to the
# ISO week; a manual build can leave it alone).
ARG REFRESH_WEEK=0

RUN echo "cache epoch: ${REFRESH_WEEK}" && apt-get update && apt-get install -y --no-install-recommends \
    python3-pip python3-venv python3-dev \
    build-essential pkg-config cmake git \
    libasound2-dev libpulse-dev libsamplerate0-dev portaudio19-dev \
    libflac-dev libsoxr-dev libssl-dev libvorbis-dev libmad0-dev \
    libfaad-dev libmpg123-dev libopusfile-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /ledfx
# Pin with --build-arg LEDFX_VERSION=2.0.x for reproducible builds; empty = latest
ARG LEDFX_VERSION=
RUN python3 -m venv /ledfx/venv \
    && /ledfx/venv/bin/pip install --no-cache-dir --upgrade pip wheel setuptools \
    && /ledfx/venv/bin/pip install --no-cache-dir "ledfx${LEDFX_VERSION:+==${LEDFX_VERSION}}"

WORKDIR /build
# Copy the upstream squeezelite source (submodule: ralph-irving/squeezelite)
COPY squeezelite/ .

# Compile with optimized flags for high-end audio.
#   PULSEAUDIO   native PulseAudio output (replaces the ALSA output backend,
#                so the sink is selected with `-o <sink>` / `-o default`)
#   DSD          native DSD + DoP output
#   RESAMPLE_MP  soxr resampling, OpenMP multi-threaded (implies RESAMPLE)
#   VISEXPORT    shared-memory export for visualisers
#   OPUS         native Opus decoding (opusfile.h lives in /usr/include/opus)
#   USE_SSL      https streams / LMS over TLS
#   NO_SSLSYM    link libssl directly; the runtime dlopen path only probes
#                libssl.so.1.x, which does not exist on Debian trixie
# FLAC, Vorbis, MP3 (mad/mpg123) and AAC (faad) are always compiled in.
# LDADD is intentionally NOT overridden - the Makefile derives it from OPTS,
# and a command-line LDADD silently discards every `LDADD +=` in the Makefile.
RUN make clean && \
    make -j"$(nproc)" OPTS="-DPULSEAUDIO -DDSD -DRESAMPLE_MP -DVISEXPORT -DOPUS -DUSE_SSL -DNO_SSLSYM -I/usr/include/opus"

# Fail the build if any flag silently did not take effect (a typo in OPTS is
# otherwise ignored by make and only shows up as a missing feature at runtime)
RUN BUILD_OPTS="$(./squeezelite -? 2>&1 | grep '^Build options:')" && \
    echo "$BUILD_OPTS" && \
    for f in LINUX PULSEAUDIO RESAMPLE_MP DSD OPUS VISEXPORT SSL; do \
        echo "$BUILD_OPTS" | grep -qw "$f" || { echo "ERROR: build option $f not enabled" >&2; exit 1; }; \
    done


# --- Stage 2: Runtime ---
FROM debian:trixie-slim

ARG REFRESH_WEEK=0

# Runtime shared libraries only - no -dev packages, no toolchain. The codecs
# below are dlopen()ed by soname, so a missing one fails silently at play time.
RUN echo "cache epoch: ${REFRESH_WEEK}" && apt-get update && apt-get install -y --no-install-recommends \
    pulseaudio pulseaudio-utils libasound2-plugins alsa-utils \
    libflac14 libvorbisfile3 libmad0 libfaad2 libmpg123-0 libopusfile0 \
    libsoxr0 libssl3 libasound2 libportaudio2 libsamplerate0 \
    python3 ca-certificates \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=snapcast /debs/snapclient.deb /debs/snapserver.deb /tmp/
RUN apt-get update \
    && apt-get install -y --no-install-recommends /tmp/snapclient.deb /tmp/snapserver.deb \
    && rm -f /tmp/*.deb && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=builder /ledfx/venv /ledfx/venv
COPY --from=builder /build/squeezelite /usr/local/bin/squeezelite

# Route ALSA clients through PulseAudio. Baked in at build time so the
# container does not need write access to /etc at runtime.
RUN printf 'pcm.!default { type pulse }\nctl.!default { type pulse }\n' > /etc/asound.conf

# Verify the runtime image can actually satisfy squeezelite: libssl/libcrypto
# and libpulse are linked directly, so a missing one stops the binary from
# starting at all; the codecs are dlopen()ed and would fail only at play time.
RUN ldd /usr/local/bin/squeezelite && \
    ! ldd /usr/local/bin/squeezelite 2>&1 | grep -q "not found" && \
    for lib in libFLAC.so libvorbisfile.so.3 libmad.so.0 libmpg123.so.0 \
               libfaad.so.2 libopusfile.so.0 libsoxr.so.0 libpulse.so.0; do \
        ldconfig -p | grep -q "$lib" || { echo "ERROR: $lib missing from runtime image" >&2; exit 1; }; \
    done && \
    /usr/local/bin/squeezelite -? | grep '^Build options:'

ENV PATH="/ledfx/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

WORKDIR /
COPY snapserver.conf /etc/snapserver.conf
COPY startup.py /startup.py

# Run unprivileged. UID/GID 1000 is the default because it matches the first
# desktop/service user on most hosts, which is what owns the bind-mounted
# config directories; if yours differs, override with `user: "<uid>:<gid>"`
# in compose (and chown the mounts to match). The audio group is for the
# optional /dev/snd passthrough used by the snapclient role.
RUN groupadd -g 1000 ledfx && \
    useradd -u 1000 -g 1000 -G audio -M -s /usr/sbin/nologin ledfx && \
    install -d -o 1000 -g 1000 /home/ledfx /home/ledfx/.ledfx /config

# PulseAudio and LedFx both keep state under $HOME, which must be writable
ENV HOME=/home/ledfx

USER 1000:1000

# find exits 0 whether or not anything matched, so the match itself has to be
# tested - otherwise a stale health file still reports healthy
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD find /tmp/supervisor_health -mmin -1 | grep -q . || exit 1

ENTRYPOINT ["python3", "-u", "/startup.py"]
