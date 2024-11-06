#!/usr/bin/env sh

# Set default ROLE to 'server' if not set
ROLE=${ROLE:-server}

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
        exec /usr/bin/snapclient -h $HOST $EXTRA_ARGS
        ;;
    client-ledfx)
        echo "Starting in client-ledfx mode..."
        # Run the snapclient in the background
        /usr/bin/snapclient -h $HOST $EXTRA_ARGS &
        # Start ledfx in the foreground
        cd /ledfx && exec /bin/sh -c '. /ledfx/venv/bin/activate && exec ledfx'
        ;;
    *)
        echo "Usage: ROLE={server|client|client-ledfx} [args]"
        exit 1
        ;;
esac
