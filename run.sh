#!/bin/bash
cd "$(dirname "$0")"

PIDFILE=".gunicorn.pid"
APP="app:app"

start() {
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "Already running (PID $(cat "$PIDFILE"))"
        return 1
    fi
    source .venv/bin/activate
    gunicorn "$APP" -p "$PIDFILE" --daemon
    sleep 0.5
    if [ -f "$PIDFILE" ]; then
        echo "Started (PID $(cat "$PIDFILE"))"
    else
        echo "Failed to start"
        return 1
    fi
}

stop() {
    if [ ! -f "$PIDFILE" ] || ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "Not running"
        rm -f "$PIDFILE"
        return 1
    fi
    kill "$(cat "$PIDFILE")"
    rm -f "$PIDFILE"
    echo "Stopped"
}

restart() {
    stop
    sleep 1
    start
}

case "${1:-start}" in
    start)   start   ;;
    stop)    stop    ;;
    restart) restart ;;
    *)       echo "Usage: $0 {start|stop|restart}" ;;
esac
