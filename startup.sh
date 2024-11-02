#!/usr/bin/env sh

# Set default ROLE to 'server' if not set
ROLE=${ROLE:-server}

# Execute the appropriate application based on the ROLE variable
case "$ROLE" in
    server)
        dbus-daemon --system
        avahi-daemon --no-chroot &
        /usr/bin/snapserver $EXTRA_ARGS
        ;;
    client)
        /usr/bin/snapclient -h $HOST $EXTRA_ARGS
        ;;
    *)
        echo "Usage: ROLE={server|client} [args]"
        exit 1
        ;;
esac