# ADB Scripts

A collection of Android ADB scripts that I have used at least once. For all of these you'll at least need `adb` installed (or just on your PATH). On Debian based system you can do:

```
sudo apt install adb
```

## OCR Text Extractor

Automates the simple process of getting text from an Android screen, swiping and repeating.

### Installation

Make sure you have `adb` on the `PATH` variable and `tesseract` installed on the system

### Usage

1. Configure the variables near the top of `ocr-text-extractor.sh`
2. Open the Android to the screen you want to extract ocr text from
3. Plug in the phone
4. Run the script with `~/path/to/adb-scripts/ocr-text-extractor.sh`

## File Sync

This script is pretty specific to me, but can easily be modified for your own use. I use it to pull Camera photos from my dumbphone (TCL Flip 2) to my computer and push `.html` web-apps to the phone (since APKs cannot be installed).

### Usage

1. Customize the variables at the top of the `file-sync.sh` script. E.g. `LOCAL_PHOTOS_DIR="$HOME/Pictures/Phone_Photos"`
2. Plug in your Android phone. Ensure USB debugging is already enabled and authorized with this machine.
3. Run the script `./file-sync.sh`
