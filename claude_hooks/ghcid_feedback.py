# /// script
# dependencies = [
#   "requests<3",
#   "rich",
# ]
# ///

import os
import re
import subprocess
import sys
import time


def get_repo_name():
    """Get the repository name from the current directory."""
    return os.path.basename(os.getcwd())

def get_pid_file_path():
    """Get the path to the PID file."""
    repo_name = get_repo_name()
    return f"/tmp/ghcid_feedback-{repo_name}.pid"

def get_output_file_path():
    """Get the path to the output file."""
    repo_name = get_repo_name()
    return f"/tmp/ghcid_feedback-{repo_name}.log"

def is_process_running(pid :int):
    """Check if a process with the given PID is still running."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def start_ghcid_if_needed():
    """Start ghcid if it's not already running."""
    pid_file = get_pid_file_path()
    output_file = get_output_file_path()
    
    # Check if there's already a running process
    if os.path.exists(pid_file):
        try:
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            if is_process_running(pid):
                return  # Process is already running
        except (ValueError, IOError):
            pass  # Invalid PID file, continue to start new process
    
    # Start new ghcid process
    print("Starting ghcid...")
    cmd = ["stack", "exec", "ghcid", "--", f"--outputfile={output_file}"]
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Save PID to file
    with open(pid_file, 'w') as f:
        _ = f.write(str(process.pid))

def wait_for_output_update(output_file : str, timeout:int=20):
    """Wait for the output file to be updated, polling every 0.1 seconds."""
    start_time = time.time()
    initial_mtime = None
    
    # Get initial modification time if file exists
    if os.path.exists(output_file):
        initial_mtime = os.path.getmtime(output_file)
    
    while time.time() - start_time < timeout:
        if os.path.exists(output_file):
            current_mtime = os.path.getmtime(output_file)
            if initial_mtime is None or current_mtime > initial_mtime:
                return True
        time.sleep(0.1)
    
    return False

def read_output_file(output_file : str):
    """Read the content of the output file."""
    try:
        with open(output_file, 'r') as f:
            return f.read().strip()
    except IOError:
        return ""

def find_haskell_files():
    """Find all Haskell files in the current directory tree."""
    haskell_files = []
    for root, dirs, files in os.walk("."):
        for file in files:
            if file.endswith((".hs", ".lhs")):
                haskell_files.append(os.path.join(root, file))
    return haskell_files

def main():
    """Main function."""
    script_start_time = time.time()
    output_file = get_output_file_path()
    
    # Start ghcid if needed
    start_ghcid_if_needed()
    
    # Check if any Haskell files are newer than the last output file
    haskell_files = find_haskell_files()
    output_file_mtime = 0
    
    if os.path.exists(output_file):
        output_file_mtime = os.path.getmtime(output_file)
    
    newer_haskell_files = []
    for haskell_file in haskell_files:
        if os.path.exists(haskell_file):
            file_mtime = os.path.getmtime(haskell_file)
            if file_mtime > output_file_mtime:
                newer_haskell_files.append(haskell_file)
    
    print(f"Found {len(haskell_files)} Haskell files, {len(newer_haskell_files)} newer than last output (output_mtime: {output_file_mtime})")
    if newer_haskell_files:
        print(f"Newer files: {newer_haskell_files}")
    
    if not newer_haskell_files:
        print("No Haskell files newer than last output, exiting.")
        sys.exit(0)
    # Check if output file was updated since script started
    file_updated = False
    if os.path.exists(output_file):
        file_mtime = os.path.getmtime(output_file)
        if file_mtime >= script_start_time:
            file_updated = True
    
    # If file wasn't updated, wait for updates
    if not file_updated:
        if not wait_for_output_update(output_file):
            print("Timeout waiting for ghcid output", file=sys.stderr)
            sys.exit(0)
    
    # Read and print the output
    output = read_output_file(output_file)
    print(output)
    
    # Check if output indicates success
    if re.match(r"^All good.*", output):
        sys.exit(0)
    else:
        sys.exit(2)

if __name__ == "__main__":
    main()
