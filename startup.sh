#!/usr/bin/env sh

# Set default ROLE to 'server' if not set
ROLE=${ROLE:-server}

# Function to keep a command running with restart on crash and log output
keep_alive() {
    cmd="$1"
    shift
    while true; do
        echo "Starting process: $cmd $@"
        $cmd "$@" 2>&1   # Run the command and capture all output
        echo "Process $cmd $@ crashed with exit code $?. Restarting in 5 second..."
        sleep 5
    done
}

# Execute the appropriate application based on the ROLE variable
case "$ROLE" in
    server)
        echo "Starting in server mode..."

        if [ ! -f /config/snapserver.conf ]; then
            cp /etc/snapserver.conf /config/snapserver.conf
            echo "Default configuration copied to /config/snapserver.conf."
        else
            echo "Configuration file already exists in /config/snapserver.conf"
        fi

        dbus-daemon --system
        avahi-daemon --no-chroot &
        exec /usr/bin/snapserver -c /config/snapserver.conf ${EXTRA_ARGS} 2>&1
        ;;
    client)
        echo "Starting in client mode..."
        keep_alive /usr/bin/snapclient -h "$HOST" ${EXTRA_ARGS}
        ;;
    ledfx)
        echo "Starting in client-ledfx mode..."
        echo "Run on host machine 'sudo modprobe snd-aloop'"

        (
            if [ -z "${EXTRA_ARGS}" ]; then
                EXTRA_ARGS='--sound alsa --soundcard Loopback --hostID LedFX'
                echo "Setting default EXTRA_ARGS: ${EXTRA_ARGS}"
            else
                echo "EXTRA_ARGS is set as: ${EXTRA_ARGS}"
            fi

            keep_alive /usr/bin/snapclient -h "${HOST}" ${EXTRA_ARGS}
        ) &
        snapclient_pid=$!

        (
            cd /ledfx
            keep_alive /bin/sh -c '. /ledfx/venv/bin/activate && exec ledfx'
        ) &
        ledfx_pid=$!

        # Wait for either process to terminate
        wait -n $snapclient_pid $ledfx_pid

        # If any process exits, kill the other and exit
        echo "One of the processes has exited. Stopping both."
        kill $snapclient_pid $ledfx_pid
        wait
        ;;
    *)
        echo "Usage: ROLE={server|client|ledfx} [args]"
        exit 1
        ;;
esac
