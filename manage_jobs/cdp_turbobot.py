import sys
import json
import time
import threading
import select
from seleniumbase import sb_cdp

url = "https://th.turboroute.ai/#/login?redirect=%2Fgrab-single%2Fsingle-hall"
urlMock = "http://127.0.0.1:5500/SeleniumBase/manage_jobs/mockTable.html"
sb = None

def turbo_login(username, password):
    global sb
    print(f"[TurboLogin] Logging in as: {username, password}")

    # Try to start the browser if not already started
    if sb is None:
        try:
            sb = sb_cdp.Chrome(urlMock, incognito=True)
        except Exception as e:
            print(f"Failed to start browser: {e}")
            sb = None
            raise
    sb.maximize()
    sb.sleep(2)
    sb.solve_captcha()
    # accountID = 'input[placeholder="Account ID"]'
    # accountPW = 'input[placeholder="Password"]'
    # sb.type(accountID, username)
    # sb.type(accountPW, password)
    # sb.click('button:contains(" Login ")')
    # sb.sleep(2)
    # sb.click('label:contains("TH")')
    
def turbo_manual_Task(job):
    """
    Receive job data from the Electron UI (Management page).
    job keys: id, region, vehicleType, startDestination
    """
    print(f"[TurboManualTask] Received job #{job.get('id')}:")
    print(f"  Region:           {job.get('region')}")
    print(f"  Vehicle Type:     {job.get('vehicleType')}")
    print(f"  Start Destination:{job.get('startDestination')}")
    # TODO: Implement actual automation steps for the manual task
    


def listen_for_commands():
    """
    Listen on stdin for JSON commands from the Electron main process.
    Each line is a JSON object representing a job/task.
    """
    print("[TurboBot] Listening for commands on stdin...", flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            job = json.loads(line)
            print(f"[TurboBot] Received command: {job}", flush=True)
            turbo_manual_Task(job)
        except json.JSONDecodeError as e:
            print(f"[TurboBot] Invalid JSON: {e}", flush=True)
        except Exception as e:
            print(f"[TurboBot] Error processing command: {e}", flush=True)
    print("[TurboBot] Stdin closed, stopping command listener.", flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: cdp_turbobot.py <username> <password>")
        sys.exit(1)
    username = sys.argv[1]
    password = sys.argv[2]
    turbo_login(username, password)

    # Start listening for manual task commands from Electron in a background thread
    cmd_thread = threading.Thread(target=listen_for_commands, daemon=True)
    cmd_thread.start()

    # Keep-alive: monitor browser window
    try:
        while True:
            time.sleep(1)
            try:
                _ = sb.get_title()
            except Exception:
                print("Browser window closed. Exiting...")
                break
    finally:
        try:
            sb.driver.stop()
        except Exception:
            pass