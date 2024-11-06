#!/usr/bin/env sh

# Set default ROLE to 'server' if not set
ROLE=${ROLE:-server}

# Function to keep a command running with restart on crash
keep_alive() {
    while true; do
        "$@"   # Run the command
        echo "Process $@ crashed with exit code $?. Restarting in 1 second..."
        sleep 1
    done
}

# Execute the appropriate application based on the ROLE variable
case "$ROLE" in
    server)
        echo "Starting in server mode..."
        dbus-daemon --system
        avahi-daemon --no-chroot &
        exec /usr/bin/snapserver $EXTRA_ARGS
        ;;
    client)
        echo "Starting in client mode..."
        exec /usr/bin/snapclient -h "$HOST" $EXTRA_ARGS
        ;;
    ledfx)
        echo "Starting in client-ledfx mode..."
        echo "Run on host machine 'sudo modprobe snd-aloop'"

        # Start snapclient in a restartable loop
        keep_alive /usr/bin/snapclient -h "$HOST" --sound alsa --soundcard "Loopback" &

        # Start ledfx in a restartable loop
        cd /ledfx && keep_alive /bin/sh -c '. /ledfx/venv/bin/activate && exec ledfx'
        ;;
    *)
        echo "Usage: ROLE={server|client|ledfx} [args]"
        exit 1
        ;;
esac
