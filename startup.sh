#!/usr/bin/env sh

# Set default ROLE to 'server' if not set
ROLE=${ROLE:-server}

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
        /usr/bin/snapclient -h "$HOST" ${EXTRA_ARGS}
        ;;
    ledfx)
        echo "Starting in client-ledfx mode..."
        echo "Run on host machine 'sudo modprobe snd-aloop'"

        # Launch the processes in the background
        (
            if [ -z "${EXTRA_ARGS}" ]; then
                EXTRA_ARGS='--sound alsa --soundcard Loopback --hostID LedFX'
                echo "Setting default EXTRA_ARGS: ${EXTRA_ARGS}"
            else
                echo "EXTRA_ARGS is set as: ${EXTRA_ARGS}"
            fi

            /usr/bin/snapclient -h "${HOST}" ${EXTRA_ARGS}
        ) &
        snapclient_pid=$!

        (
            cd /ledfx
            . /ledfx/venv/bin/activate
            exec /ledfx/venv/bin/ledfx
        ) &
        ledfx_pid=$!

        # Wait for any process to exit
        wait $snapclient_pid $ledfx_pid

        # If any process exits, terminate the other and exit the script
        echo "One of the processes has exited. Stopping both."
        kill $snapclient_pid $ledfx_pid
        wait
        exit 1
        ;;
    *)
        echo "Usage: ROLE={server|client|ledfx} [args]"
        exit 1
        ;;
esac
