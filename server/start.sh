#!/data/data/com.termux/files/usr/bin/bash
# Starts the FNAF AR offline server inside Termux.
# Stop it with CTRL (on the Termux extra-keys row) + c.
cd "$(dirname "$0")" || exit 1
command -v termux-wake-lock >/dev/null && termux-wake-lock
echo "FNAF AR server starting. Leave Termux running, go to the home screen and open the game."
python server.py offline
command -v termux-wake-unlock >/dev/null && termux-wake-unlock
