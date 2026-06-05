#!/usr/bin/env bash

# ==============================================================================
# SCRIPT CONFIGURATION
# ==============================================================================

# Push files onto the device
SKIP_PUSH_APPS='false'
LOCAL_APPS_DIR="$HOME/dev/single-file-web-apps/dist"
DEVICE_APPS_DIR="/sdcard/Apps/"

# Pull files from the device
SKIP_PULL_PHOTOS='false'
LOCAL_PHOTOS_DIR="$HOME/Pictures/Phone_Photos"
DEVICE_PHOTOS_DIR="/sdcard/DCIM/Camera"

# ==============================================================================
# SAFETY AND RUNTIME CHECKS (Best Practices)
# ==============================================================================
# Exit immediately if a command exits with a non-zero status, if an unassigned 
# variable is evaluated, or if any command in a pipeline fails.
set -euo pipefail

# Check if adb command-line tool is installed
if ! command -v adb &> /dev/null; then
    echo "[-] Error: 'adb' utility is not installed or not in your PATH."
    exit 1
fi

echo "[*] Checking for connected ADB device..."
# Wait for the phone to be plugged in and authorized via USB debugging
adb wait-for-device

echo "[+] Device detected successfully!"
echo "=================================================================="

# Ensure local directories exist on your machine
mkdir -p "$LOCAL_APPS_DIR"
mkdir -p "$LOCAL_PHOTOS_DIR"

# Ensure the destination directory exists on the phone
# (mkdir -p avoids throwing errors if the directory already exists)
adb shell mkdir -p "$DEVICE_APPS_DIR"

# ==============================================================================
# PHASE 1: PUSH APPS (Computer -> Phone)
# ==============================================================================
if [[ "${SKIP_PUSH_APPS}" == 'false' ]]; then
    echo "[*] Phase 1: Syncing HTML web apps to phone..."

    # Using --sync ensures ADB only uploads new or modified .html files.
    # The trailing '/.' copies the *contents* of the folder rather than nesting it.
    if adb push --sync "$LOCAL_APPS_DIR/." "$DEVICE_APPS_DIR" &> /dev/null; then
        echo "[+] Web apps sync complete."
    else
        # Fallback if your local adb binary version is older and lacks '--sync'
        echo "[!] Adb '--sync' flag unavailable or failed. Falling back to default push..."
        adb push "$LOCAL_APPS_DIR/." "$DEVICE_APPS_DIR"
    fi
fi
# ==============================================================================
# PHASE 2: PULL PHOTOS (Phone -> Computer)
# ==============================================================================
if [[ "${SKIP_PULL_PHOTOS}" == 'false' ]]; then
    echo "[*] Phase 2: Auditing phone directory for new photos..."

    NEW_PHOTOS_COUNT=0

    # Using <( ... ) passes the file list safely into the loop without a pipe stream
    while read -r filename; do
        # Ensure line isn't blank and skip hidden configuration files
        if [ -n "$filename" ] && [[ ! "$filename" =~ ^\. ]]; then
            LOCAL_FILE_PATH="$LOCAL_PHOTOS_DIR/$filename"
            
            # If the photo doesn't exist on the computer yet, grab it
            if [ ! -f "$LOCAL_FILE_PATH" ]; then
                echo "    -> Downloading new file: $filename"
                
                # Adding </dev/null strictly forces ADB to ignore the loop's input stream
                adb pull "$DEVICE_PHOTOS_DIR/$filename" "$LOCAL_FILE_PATH" > /dev/null </dev/null
                
                # Using standard bash arithmetic safely outside of a subshell
                NEW_PHOTOS_COUNT=$((NEW_PHOTOS_COUNT + 1))
            fi
        fi
    done < <(adb shell "ls -1 $DEVICE_PHOTOS_DIR" | tr -d '\r')

    if [ "$NEW_PHOTOS_COUNT" -eq 0 ]; then
        echo "[+] Computer photos are already completely up to date."
    else
        echo "[+] Done! Downloaded $NEW_PHOTOS_COUNT new media file(s)."
    fi
fi

echo "=================================================================="
echo "[+] Sync synchronization engine finished successfully!"