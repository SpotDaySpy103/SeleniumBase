import sys
import json
import time
import threading
import select
from seleniumbase import sb_cdp
from selenium.common.exceptions import TimeoutException

url = "https://th.turboroute.ai/#/login?redirect=%2Fgrab-single%2Fsingle-hall"
urlMock = "http://127.0.0.1:5500/SeleniumBase/manage_jobs/mockTable.html"
sb = None

def turbo_login(username, password):
    global sb
    print(f"[TurboLogin] Logging in as: {username, password}")
    try:
        # Try to start the browser if not already started
        if sb is None:
            try:
                sb = sb_cdp.Chrome(url, incognito=True)
            except Exception as e:
                print(f"Failed to start browser: {e}")
                sb = None
                raise
        sb.maximize()
        sb.sleep(2)
        sb.solve_captcha()
        accountID = 'input[placeholder="Account ID"]'
        accountPW = 'input[placeholder="Password"]'
        sb.type(accountID, username)
        sb.type(accountPW, password)
        sb.click('button:contains(" Login ")')
        sb.sleep(2)
        sb.click('label:contains("TH")')
    except Exception as e:
        print(f"[TurboLogin] Login failed: {e}")
    
def turbo_manual_Task(job):
    """
    Receive job data from the Electron UI (Management page).
    Returns result by printing a JSON line to stdout (read by Electron).
    """
    global sb
    jobID = job.get('id')
    jobRegion = job.get('region')
    jobVehicleType = job.get('vehicleType')
    jobDest = job.get('startDestination')

    if sb is None:
        send_result(jobID, "failed", "Browser not initialized. Login first.")
        return

    try:
        # TODO: Implement actual automation steps here
        print(f"[TurboManualTask] Processing job #{jobID}: {jobRegion}, {jobVehicleType}, {jobDest}", flush=True)
        time.sleep(2)
        match_found = False

		# Set timeout for search rows
        search_timeout = 60  # seconds
        search_start_time = time.time()
        
        tables_result = turbo_get_tables()
        if not isinstance(tables_result, tuple):
            return tables_result
        elementsDest, elementsRegion, elementsVehicle, elementsSelect = tables_result
        
        while not match_found and (time.time() - search_start_time) < search_timeout:
            for i, elem in enumerate(elementsDest):
                dest_text = elem.text.strip()
                parts = dest_text.split('-') # Split '-' to get the first part as destination
                destOneCus = parts[0] if len(parts) > 0 else '' # Get the first part as destination
                region_text = elementsRegion[i].text.strip() if i < len(elementsRegion) else "N/A"
                vehicle_text = elementsVehicle[i].text.strip() if i < len(elementsVehicle) else "N/A"
                select_text = elementsSelect[i].text.strip() if i < len(elementsSelect) else "N/A"
                print(f"Row {i}: Dest='{dest_text}', Region='{region_text}', Vehicle='{vehicle_text}', Select='{select_text}'", flush=True)
                
                # Random destination matches any row, so we can ignore destination when matching if jobDest is "Random"
                if jobDest == "Random":
                    if vehicle_text == jobVehicleType and region_text == jobRegion:
                        print(f"--> Match found for job #{jobID} at row {i} with random destination (vehicle_text='{vehicle_text}' = jobVehicleType='{jobVehicleType}' AND region_text='{region_text}' = jobRegion='{jobRegion}')", flush=True)
                        match_found = True
                        sb.sleep(0.5)
                        # Click the select button in this row
                        if i < len(elementsSelect):
                            try:
                                elementsSelect[i].mouse_click()
                                sb.sleep(3) 
                                print(f"Clicked select for job #{jobID} at row {i}", flush=True)
                                sb.sleep(3)
                                sb.wait_for_element('button[data-v-50b69d50] span:contains("แข่งขันรับงาน")', timeout=15)
                                sb.sleep(0.8)
                                sb.highlight_overlay('button[data-v-50b69d50] span:contains("แข่งขันรับงาน")')
                                sb.sleep(1)
                                send_result(jobID, "completed", f"{dest_text}")
                            except Exception as e:
                                print(f"Failed to click select for job #{jobID} at row {i}: {e}", flush=True)
                                send_result(jobID, "failed", f"{dest_text}")
                        else:
                            print(f"No select element for row {i} while processing job #{jobID}", flush=True)
                        break
                if destOneCus == jobDest:
                    if vehicle_text == jobVehicleType:
                        if region_text == jobRegion:
                            print(f"--> Match found for job #{jobID} at row {i} with exact destination (destOneCus='{destOneCus}' = jobDest='{jobDest}' AND vehicle_text='{vehicle_text}' = jobVehicleType='{jobVehicleType}' AND region_text='{region_text}' = jobRegion='{jobRegion}')", flush=True)
                            match_found = True
                            sb.sleep(0.5)
                            # Click the select button in this row
                            if i < len(elementsSelect):
                                try:
                                    elementsSelect[i].mouse_click()
                                    print(f"Clicked select for job #{jobID} at row {i}", flush=True)
                                    sb.sleep(3)
                                    sb.wait_for_element('button[data-v-50b69d50] span:contains("แข่งขันรับงาน")', timeout=15)
                                    sb.sleep(5)
                                    sb.highlight_overlay('button[data-v-50b69d50] span:contains("แข่งขันรับงาน")')
                                    #app > div > div.main-container > div.app-main > div > div:nth-child(4) > div > div.el-dialog__footer > div > button[data-v-50b69d50] span:contains("แข่งขันรับงาน")
                                    # highlight this Xpath //*[@id="app"]/div/div[2]/div[2]/div/div[3]/div/div[3]/div/button/span
                                    send_result(jobID, "completed", f"{dest_text}")
                                except Exception as e:
                                    print(f"Failed to click select for job #{jobID} at row {i}: {e}", flush=True)
                                    send_result(jobID, "failed", f"{dest_text}")
                            else:
                                print(f"No select element for row {i} while processing job #{jobID}", flush=True)
                            break
            # If not found in this iteration, wait before refetching
            if not match_found:
                elapsed = time.time() - search_start_time
                remaining = search_timeout - elapsed
                if remaining > 0:
                    print(f"No match found. Waiting 2 seconds before refetching... ({remaining:.1f}s remaining)", flush=True)
                    time.sleep(2)
                    
        # After timeout
        if not match_found:
            print(f"✗ No match found after {search_timeout} seconds timeout", flush=True)
            send_result(jobID, "failed", f"No match found after {search_timeout} seconds timeout")
    except Exception as e:
        send_result(jobID, "failed", str(e))

def turbo_get_tables():
    global sb
    try:
        elementsDest = sb.find_elements('td[class*="el-table_1_column_2"]', timeout=30)
        elementsRegion = sb.find_elements('td[class*="el-table_1_column_4"]', timeout=30)
        elementsVehicle = sb.find_elements('td[class*="el-table_1_column_5"]', timeout=30)
        elementsSelect = sb.find_elements('td[class*="el-table_1_column_13"] span', timeout=30) #'td[class*="el-table_1_column_13"] span'
        return elementsDest, elementsRegion, elementsVehicle, elementsSelect
    except TimeoutException as e:
        fail_msg = f"FAIL: Timed out waiting for table columns: {e}"
        print(fail_msg, flush=True)
        return fail_msg, 504
    except Exception as e:
        fail_msg = f"FAIL: Error while fetching table columns: {e}"
        print(fail_msg, flush=True)
        return fail_msg, 500

def send_result(job_id, status, message=""):
    """
    Print a structured JSON result line to stdout.
    Electron main process parses this to update the UI.
    """
    result = json.dumps({
        "type": "task_result",
        "id": job_id,
        "status": status,
        "message": message,
    })
    print(result, flush=True)
    

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
        time.sleep(2)
        try:
            if sb is None or sb.driver is None:
                raise Exception("Browser reference lost")
            # Check browser is still alive via its internal connection
            if hasattr(sb.driver, 'browser') and sb.driver.browser is None:
                raise Exception("Browser connection lost")
        except Exception:
            print("[TurboBot] Browser window closed. Exiting...", flush=True)
            break
finally:
    try:
        if sb is not None and sb.driver is not None:
            sb.driver.stop()
    except Exception:
        pass