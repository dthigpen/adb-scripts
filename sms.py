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
DEFAULT_DEVICE_LOG_FILE = '/sdcard/Documents/sent_sms.txt'

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
    """Queries phone book entries and serializes them into a local JSON map using explicit string keys."""
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
                raw_num = re.sub(r'\D', '', num_match.group(1))
                
                # Explicitly force the 10-digit segment as a clean string key
                num_10 = str(raw_num[-10:] if len(raw_num) >= 10 else raw_num)
                
                if name and num_10:
                    # Store alphabetical key
                    contacts[name.lower()] = {"name": name, "number": num_10}
                    # Store 10-digit key strictly as a string entry
                    contacts[num_10] = {"name": name, "number": num_10}

    with open(CACHE_FILE, 'w') as f:
        json.dump(contacts, f, indent=4)
    return contacts

def get_contact(target, cache):
    """
    Looks up a target (name or number) in the cache.
    Returns the entry dict {"name": "...", "number": "..."} if found, or None.
    """
    target_clean = str(target).strip()
    if not target_clean:
        return None

    # Case 1: Try checking as an alphabetical contact name key
    if target_clean.lower() in cache:
        return cache[target_clean.lower()]

    # Case 2: Try checking as a phone number key normalized to 10 digits
    num_only = re.sub(r'\D', '', target_clean)
    num_10 = num_only[-10:] if len(num_only) >= 10 else num_only
    
    if num_10 in cache:
        return cache[num_10]

    return None

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
    
    # Check our new dictionary-returning lookup function
    contact = get_contact(target, cache)
    
    if contact:
        # Match found: use the clean 10-digit number from the cache
        resolved_number = contact["number"]
        display_name = contact["name"]
    else:
        # No match: Check if the user passed a raw phone number or a broken contact name
        # If the target string contains any alphabetic characters, it's an invalid contact name
        if re.search(r'[a-zA-Z]', target):
            print(f"[-] Error: '{target}' does not exist in your contacts cache.", file=sys.stderr)
            print("    Run './adb_sms.py contacts' to verify your available mappings.", file=sys.stderr)
            sys.exit(1)
            
        # If it doesn't contain letters, treat it as a raw phone number input
        resolved_number = target
        display_name = "Unknown Contact"
    
    # Standardize the final destination number for the cellular radio layer
    clean_num = re.sub(r'\D', '', resolved_number)
    if len(clean_num) == 10:
        clean_num = f"+1{clean_num}"
    elif len(clean_num) == 11 and clean_num.startswith("1"):
        clean_num = f"+{clean_num}"

    print(f"[*] Delivering message to {display_name} ({clean_num})...")
    
    # Escape the message string securely for the remote shell environment
    escaped_message = shlex.quote(message)
    
    # Execute the hardware transaction over the ADB pipe
    run_adb(["shell", "service", "call", "isms", "5", "i32", "1", 
             "s16", "com.android.mms", "s16", "null", 
             "s16", clean_num, "s16", "null", 
             "s16", escaped_message, "s16", "null", "s16", "null", 
             "i32", "0", "i64", "0"])
    
    # Handle the device text file tracking append routine
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

            raw_sender = sender_m.group(1).strip() if sender_m else "Unknown"
            body = body_m.group(1) if body_m else ""
            raw_date = date_m.group(1).strip() if date_m else ""

            # Extract the core 10 digits from the incoming sender address
            clean_sender_digits = re.sub(r'\D', '', raw_sender)
            sender_10 = clean_sender_digits[-10:] if len(clean_sender_digits) >= 10 else clean_sender_digits

            # Resolve using our clean 10-digit string
            contact = get_contact(sender_10, cache)
            if contact:
                # If found, make it look nice: "Jane Doe (+11234567890)"
                display_sender = f"{contact['name']} ({raw_sender})"
            else:
                # Fallback case: just print the raw number "+11234567890"
                display_sender = raw_sender

            # Date translation formatting
            formatted_date = "Unknown"
            if raw_date.isdigit():
                unix_secs = int(raw_date) / 1000
                formatted_date = datetime.fromtimestamp(unix_secs).strftime('%Y-%m-%d %H:%M')

            output_line = f"[{formatted_date}] \033[1;32m{display_sender}\033[0m: {body}"
            
            # The filter now successfully evaluates against the resolved contact name
            if args.filter:
                if args.filter.lower() in output_line.lower():
                    output_lines.append(output_line)
            else:
                output_lines.append(output_line)

            if len(output_lines) >= 12:
                break

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
        default=DEFAULT_DEVICE_LOG_FILE,
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
        # sys.exit(0)

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