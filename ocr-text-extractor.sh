#!/usr/bin/env bash

# Extracts text from an Android screen in repetition

set -Eeuo pipefail
IFS=$'\n\t'
function msg {
  echo >&2 -e "${@-}"
}

# CONFIGURE THESE AS YOU WISH
BASE_DIR="${PWD}"
SESSION_NAME='extracted_text' # any non-alphanumeric characters get converted to _
MAX_ITERATIONS=1000
USE_UNIQUE_SESSIONS=true # will append current timestamp so that existing session dir does not get overwritten
declare -a ITERATION_ACTION_CMDS=('adb shell input swipe 780 1150 300 1150')
# ---------------

function drop_first_line {
	tail -n +2
	# tail -n +3
}

function first_column {
	awk '{print $1}'
}
ADB_DEVICE_ATTEMPTS=30
ADB_DEVICE_WAIT_SEC=2

# Wait for user to connect device via adb
# Assumes one adb device will be plugged in
for((i=0 ; i<${ADB_DEVICE_ATTEMPTS} ; i++))
do
	devices="$(adb devices | drop_first_line | first_column)"
	if [[ -z "${devices}" ]]
	then
		msg "No ADB device found. Waiting ${ADB_DEVICE_WAIT_SEC}s before trying again. (Attempt $((i+1))/${ADB_DEVICE_ATTEMPTS})"
		sleep "${ADB_DEVICE_WAIT_SEC}"
	else
		msg "ADB device found:\n${devices}"
		break
	fi
done

function confirm {
  while true; do
    read -p "$1 (y/n): " yn
    case $yn in
      [Yy]* ) return 0;;
      [Nn]* ) return 1;;
      * ) echo "Please answer yes or no.";;
    esac
  done
}

# Setup output directory
start_s=$(date +%s)
clean_session_name="$(echo "${SESSION_NAME}" | sed -E 's/[^a-zA-Z0-9]{1,}/_/g')"
if [[ "${USE_UNIQUE_SESSIONS}" == true ]]
then
	SESSION_DIR="${BASE_DIR}/${clean_session_name}_${start_s}"
else
	SESSION_DIR="${BASE_DIR}/${clean_session_name}"
	if [[ -d "${SESSION_DIR}" ]]
	then
		if confirm "Are you sure you want to delete the ${SESSION_DIR} directory"
		then
			rm -rf "${SESSION_DIR}"
		fi

	fi
fi

msg "Session directory: $SESSION_DIR"
mkdir -p "${SESSION_DIR}"
pushd "${SESSION_DIR}"

all_text_filename='all_text.txt'
echo '' > "${all_text_filename}"
last_s=${start_s}
# Perform iterations
for((i=1 ; i<=${MAX_ITERATIONS} ; i++))
do
	msg "Iteration ${i} of ${MAX_ITERATIONS}"
	padded_iter=$(printf '%06d' $i)

	# Take a screenshot and save it to the computer instead of the phone
	screenshot_filename="screenshot_${padded_iter}.png"
	adb exec-out screencap -p > "${screenshot_filename}"

 	# Extract text with tesseract
	screen_text_filename_base="text_${padded_iter}"
	tesseract "${screenshot_filename}" "${screen_text_filename_base}"

	cat "${screen_text_filename_base}.txt" >> "${all_text_filename}"

	# PRE CONDITIONS
	# NOTE could check if text is present or not

	# ACTIONS
	# Run each action cmd
	for cmd in "${ITERATION_ACTION_CMDS[@]}"
	do
	   bash -c "${cmd}"
	done
	now_s=$(date +%s)
	elapsed_total_s=$(( now_s - start_s ))
	elapsed_last_s=$(( now_s - last_s ))
	msg "Total Elapsed: ${elapsed_total_s}s, Last Iteration: ${elapsed_last_s}s"
	last_s=${now_s}
done

popd
