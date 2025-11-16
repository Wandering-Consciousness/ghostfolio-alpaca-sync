#!/bin/sh
set -e

# Remove any existing lock file
rm -f /root/ghost.lock

echo "Starting Ghostfolio Alpaca Sync..."

if [ -z "$CRON" ]; then
  echo "CRON not set - running one-time sync now"
  cd /usr/app/src || exit
  python main.py
else
  echo "Setting up cron schedule: $CRON"
  echo "$CRON /root/run.sh" > /etc/crontabs/root
  echo "Next run will be scheduled by: $CRON"

  # Run once immediately
  echo "Running initial sync..."
  cd /usr/app/src || exit
  python main.py

  # Start cron daemon
  echo "Starting cron daemon..."
  crond -f -d 8
fi
