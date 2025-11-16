#!/bin/sh

LOCK_FILE=/root/ghost.lock

if [ ! -f "$LOCK_FILE" ]; then
   touch "$LOCK_FILE"
   echo "Starting Alpaca Sync - $(date)"
   cd /usr/app/src || exit
   python main.py
   rm "$LOCK_FILE"
   echo "Finished Sync - $(date)"
else
   echo "Lock file present: $LOCK_FILE"
   echo "Sync already running or previous run didn't complete properly"
   echo "Try increasing time between runs or manually remove the lock file"
fi
