# ADB Scripts

A collection of Android ADB scripts that I have used at least once

## OCR Text Extractor

Automates the simple process of getting text from an Android screen, swiping and repeating.

### Installation

Make sure you have `adb` on the `PATH` variable and `tesseract` installed on the system

### Usage

1. Configure the variables near the top of `ocr-text-extractor.sh`
2. Open the Android to the screen you want to extract ocr text from
3. Plug in the phone
4. Run the script with `~/path/to/adb-scripts/ocr-text-extractor.sh`
