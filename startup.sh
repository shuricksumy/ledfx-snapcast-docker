#!/usr/bin/env sh

set -e

ROLE=${ROLE:-server}
HOST=${HOST:-localhost}

echo "Detected ROLE: $ROLE"

get_pulseaudio_monitor() {
    # Use pacmd or pactl to find the monitor device
    monitor=$(pactl list short sources 2>/dev/null | grep '\.monitor' | head -n 1 | cut -f2)
    echo "$monitor"
}

case "$ROLE" in
    server)
        echo "Starting in server mode..."

        if [ ! -f /config/snapserver.conf ]; then
            cp /etc/snapserver.conf /config/snapserver.conf
            echo "Copied default config to /config/snapserver.conf."
        else
            echo "Found existing config at /config/snapserver.conf"
        fi

        dbus-daemon --system
        avahi-daemon --no-chroot &

        exec /usr/bin/snapserver -c /config/snapserver.conf ${EXTRA_ARGS} 2>&1
        ;;

    client)
        echo "Starting in client mode..."
        exec /usr/bin/snapclient -h "$HOST" ${EXTRA_ARGS}
        ;;

    ledfx)
        echo "Starting in client-ledfx mode..."
        echo "NOTE: On host, run: sudo modprobe snd-aloop"

        # Setup PulseAudio socket if available
        if [ -e /run/user/1000/pulse/native ]; then
            export PULSE_SERVER=unix:/run/user/1000/pulse/native
            echo "Using host PulseAudio via $PULSE_SERVER"
        fi

        # Auto-detect monitor device if Pulse is being used
        if [ -z "${EXTRA_ARGS}" ]; then
            MONITOR=$(get_pulseaudio_monitor)
            if [ -n "$MONITOR" ]; then
                EXTRA_ARGS="--sound pulse --input-device $MONITOR --hostID LedFX"
                echo "Auto-detected PulseAudio monitor: $MONITOR"
            else
                echo "WARNING: No PulseAudio monitor found. Using fallback device."
                EXTRA_ARGS="--sound pulse --input-device default --hostID LedFX"
            fi
        else
            echo "Using provided EXTRA_ARGS: ${EXTRA_ARGS}"
        fi

        # Start snapclient
        /usr/bin/snapclient -h "${HOST}" ${EXTRA_ARGS} &
        snapclient_pid=$!

        # Start LedFx
        (
            cd /ledfx
            . /ledfx/venv/bin/activate
            echo "Launching LedFx..."
            exec /ledfx/venv/bin/ledfx
        ) &
        ledfx_pid=$!

        # Wait for either process to exit
        wait -n $snapclient_pid $ledfx_pid
        echo "One of the processes exited. Cleaning up..."
        kill $snapclient_pid $ledfx_pid 2>/dev/null || true
        wait
        exit 1
        ;;

    *)
        echo "Usage: ROLE={server|client|ledfx} [args]"
        exit 1
        ;;
esac