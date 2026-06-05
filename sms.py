#!/usr/bin/env python3
import argparse
import os
import subprocess
import re
import json
import shlex
import sys
from datetime import datetime

# ==============================================================================
# CONFIGURATION & ENVIRONMENT SETUP
# ==============================================================================
CACHE_FILE = f"/tmp/adb_contacts_cache_{os.getlogin()}.json"

def run_adb(args):
    """Executes an ADB command safely and returns standard output strings."""
    try:
        cmd = ["adb"] + args
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"[-] ADB Execution Error: {e.stderr.strip()}", file=sys.stderr)
        return ""
    except FileNotFoundError:
        print("[-] Error: 'adb' executable not found in system PATH.", file=sys.stderr)
        sys.exit(1)

# ==============================================================================
# CONTACT CACHE MATRIX LOGIC
# ==============================================================================
def build_contacts_cache(force=False):
    """Queries phone book entries and serializes them into a local JSON map."""
    if not force and os.path.exists(CACHE_FILE) and os.path.getsize(CACHE_FILE) > 0:
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)

    raw_output = run_adb(["shell", "content query --uri content://com.android.contacts/data/phones --projection display_name:data1"])
    
    contacts = {}
    for line in raw_output.splitlines():
        if "Row:" in line:
            name_match = re.search(r'display_name=([^,]+)', line)
            num_match = re.search(r'data1=([^,]+)', line)
            
            if name_match and num_match:
                name = name_match.group(1).strip()
                # Extract numbers only to create a uniform lookup key
                num = re.sub(r'\D', '', num_match.group(1))
                if num.startswith("1") and len(num) == 11:
                    num = num[1:]
                
                if name and num:
                    contacts[name.lower()] = {"name": name, "number": num}
                    contacts[num] = {"name": name, "number": num}

    with open(CACHE_FILE, 'w') as f:
        json.dump(contacts, f, indent=4)
    return contacts

def resolve_target(target, cache):
    """Translates either a name string or a raw number using the local cache mapping."""
    target_clean = target.strip()
    
    if target_clean.lower() in cache:
        return cache[target_clean.lower()]["number"]
        
    num_only = re.sub(r'\D', '', target_clean)
    if num_only.startswith("1") and len(num_only) == 11:
        num_only = num_only[1:]
        
    if num_only in cache:
        return cache[num_only]["name"]
        
    return target

# ==============================================================================
# DEVICE FILE APPEND LOGGER
# ==============================================================================
def log_to_device(device_log_path, target_name, target_num, message):
    """Appends transaction metadata to a plaintext log directly on the phone."""
    if not device_log_path:
        return

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    # Format line: [Timestamp] Name (Number): Message
    log_line = f"[{timestamp}] {target_name} ({target_num}): {message}\n"
    
    # Securely escape internal quotes for the remote echo statement
    escaped_line = log_line.replace('"', '\\"').replace('`', '\\`').replace('$', '\\$')
    
    # Ensure parent directory layer exists on the file structure
    dir_path = os.path.dirname(device_log_path)
    if dir_path:
        run_adb(["shell", f"mkdir -p '{dir_path}'"])
        
    # Append the line straight to the target location on device
    run_adb(["shell", f"echo -n \"{escaped_line}\" >> '{device_log_path}'"])

# ==============================================================================
# COMMAND LINE DIRECTIVES
# ==============================================================================
def cmd_send(args, cache):
    target = args.target
    message = args.message
    
    resolved = resolve_target(target, cache)
    
    # Clean up phone number variables
    clean_num = re.sub(r'\D', '', resolved)
    if len(clean_num) == 10:
        clean_num = f"+1{clean_num}"
    elif len(clean_num) == 11 and clean_num.startswith("1"):
        clean_num = f"+{clean_num}"

    display_name = target if target.lower() in cache else resolve_target(clean_num, cache)
    if display_name == clean_num:
        display_name = "Unknown Contact"

    print(f"[*] Delivering message to {display_name} ({clean_num})...")
    
    # Bulletproof the text string using shlex.quote for the remote Android shell environment
    # This turns "It's" into "'It'\''s'" automatically so the shell parses it perfectly
    escaped_message = shlex.quote(message)
    
    # We drop the manual single quotes from f"'{message}'" and use our safely escaped string instead
    run_adb(["shell", "service", "call", "isms", "5", "i32", "1", 
             "s16", "com.android.mms", "s16", "null", 
             "s16", clean_num, "s16", "null", 
             "s16", escaped_message, "s16", "null", "s16", "null", 
             "i32", "0", "i64", "0"])
    
    # Handle the device tracking append routine
    if args.device_log.lower() != 'none':
        log_to_device(args.device_log, display_name, clean_num, message)
        print(f"[+] Message sent and logged to device at: {args.device_log}")
    else:
        print("[+] Message sent without device logging.")

def cmd_inbox(args, cache):
    raw_cursor = run_adb(["shell", "content query --uri content://sms/inbox --projection address,body,date --sort 'date DESC'"])
    
    if not raw_cursor or "No result" in raw_cursor:
        print("[!] Storage inbox layer reporting zero records.")
        return

    output_lines = []
    
    for line in raw_cursor.splitlines():
        if "Row:" in line:
            sender_m = re.search(r'address=([^,]+)', line)
            body_m = re.search(r'body=([^,]+)', line)
            date_m = re.search(r'date=([^,]+)', line)

            sender = sender_m.group(1).strip() if sender_m else "Unknown"
            body = body_m.group(1) if body_m else ""
            raw_date = date_m.group(1).strip() if date_m else ""

            display_sender = resolve_target(sender, cache)
            if display_sender != sender:
                display_sender = f"{display_sender} ({sender})"

            formatted_date = "Unknown"
            if raw_date.isdigit():
                unix_secs = int(raw_date) / 1000
                formatted_date = datetime.fromtimestamp(unix_secs).strftime('%Y-%m-%d %H:%M')

            output_line = f"[{formatted_date}] \033[1;32m{display_sender}\033[0m: {body}"
            
            if args.filter:
                if args.filter.lower() in output_line.lower():
                    output_lines.append(output_line)
            else:
                output_lines.append(output_line)

            if len(output_lines) >= 12:
                break

    # Reverse back to maintain proper prompt base views
    for line in reversed(output_lines):
        print(line)

def cmd_contacts(cache):
    printed = set()
    for val in cache.values():
        entry = f"{val['name']}: {val['number']}"
        if entry not in printed:
            print(entry)
            printed.add(entry)

# ==============================================================================
# ARGUMENT COMPILATION INTERFACE
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="ADB Unix-Style Command Line Texting Bridge for Feature Phones"
    )
    
    # Global flag adjustments
    parser.add_argument(
        "--device-log", 
        default="/sdcard/Documents/sent_sms.txt",
        help="Target text path on device for historical logging. Pass 'none' to disable entirely."
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Wipe the local contacts JSON map data and exit"
    )

    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")

    # Send Layout Subparser
    send_parser = subparsers.add_parser("send", help="Transmit a background SMS text payload")
    send_parser.add_argument("target", help="Recipient contact Name or Phone Number")
    send_parser.add_argument("message", help="The text message contents inside double quotes")

    # Inbox Layout Subparser
    inbox_parser = subparsers.add_parser("inbox", help="Fetch recent incoming message structures")
    inbox_parser.add_argument("filter", nargs="?", default="", help="Optional substring string filter (grep style)")

    # Contacts Layout Subparser
    subparsers.add_parser("contacts", help="Print all unique local directory map references")

    args = parser.parse_args()

    # Early exit parameter triggers
    if args.clear_cache:
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
        print("[+] Contacts dictionary cache cleared.")
        sys.exit(0)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Initialize active debugging target interface linkage
    subprocess.run(["adb", "wait-for-device"])
    cache = build_contacts_cache()

    if args.command == "send":
        cmd_send(args, cache)
    elif args.command == "inbox":
        cmd_inbox(args, cache)
    elif args.command == "contacts":
        cmd_contacts(cache)

if __name__ == "__main__":
    main()