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
    if isinstance(job, dict) and isinstance(job.get('jobs'), list):
        jobs = job.get('jobs', [])
    elif isinstance(job, list):
        jobs = job
    else:
        jobs = [job]

    jobs = [item for item in jobs if isinstance(item, dict)]
    if not jobs:
        print('[TurboManualTask] Invalid payload: no job data found', flush=True)
        return

    if len(jobs) > 5:
        print(f"[TurboManualTask] Received {len(jobs)} jobs. Trimming to max 5.", flush=True)
        jobs = jobs[:5]

    if len(jobs) < 1:
        print('[TurboManualTask] Received fewer than 1 job. Ignoring.', flush=True)
        return

    pause_after_click_seconds = 60
    pause_minutes_setting = jobs[0].get('pauseAfterClickMinutes')
    try:
        parsed_pause_minutes = float(pause_minutes_setting)
        if parsed_pause_minutes > 0:
            pause_after_click_seconds = parsed_pause_minutes * 60
    except (TypeError, ValueError):
        pause_seconds_setting = jobs[0].get('pauseAfterClickSeconds')
        try:
            parsed_pause_seconds = float(pause_seconds_setting)
            if parsed_pause_seconds > 0:
                pause_after_click_seconds = parsed_pause_seconds
        except (TypeError, ValueError):
            pass

    print(f"[TurboManualTask] Received {len(jobs)} job(s)", flush=True)

    if sb is None:
        for item in jobs:
            send_result(
                item.get('id'),
                "failed",
                item.get('region'),
                item.get('vehicleType'),
                "Browser not initialized. Login first.",
            )
        return

    pending_jobs = []
    now = time.time()
    for item in jobs:
        job_timeout = item.get('timeout', 10)
        try:
            timeout_minutes = float(job_timeout)
        except (TypeError, ValueError):
            timeout_minutes = 10
        if timeout_minutes <= 0:
            timeout_minutes = 10
        print(f"[TurboManualTask] Job {item}", flush=True)
        pending_jobs.append({
            "id": item.get('id'),
            "region": item.get('region'),
            "vehicleType": item.get('vehicleType'),
            "startDestination": item.get('startDestination'),
            "secondDestination": item.get('secondDestination'),
            "thirdDestination": item.get('thirdDestination'),
            "timeout_seconds": timeout_minutes * 60,
            "started_at": now,
        })

    print(f"[TurboManualTask] All jobs in pending list: {pending_jobs}", flush=True)
    print(
        f"[TurboManualTask] Added {len(pending_jobs)} job(s) to pending list with timeouts: "
        f"{[item['timeout_seconds'] for item in pending_jobs]} seconds",
        flush=True,
    )
    pause_other_jobs_until = 0

    while pending_jobs:
        now_loop = time.time()
        if pause_other_jobs_until > now_loop:
            remaining_pause = pause_other_jobs_until - now_loop
            print(
                f"[TurboManualTask] One task already clicked. Pausing other tasks for {remaining_pause:.1f}s...",
                flush=True,
            )
            time.sleep(remaining_pause)

        elementsDest, elementsRegion, elementsVehicle, elementsSelect = turbo_get_tables(pending_jobs[0]["timeout_seconds"])

        if (
            len(elementsDest) == 0
            and len(elementsRegion) == 0
            and len(elementsVehicle) == 0
            and len(elementsSelect) == 0
        ):
            print(
                "[TurboManualTask] Table fetch returned no data",
                flush=True,
            )
            current_time = time.time()
            timed_out_job_ids = set()
            for job_item in pending_jobs:
                elapsed_seconds = current_time - job_item["started_at"]
                if elapsed_seconds >= job_item["timeout_seconds"]:
                    send_result(
                        job_item["id"],
                        "failed",
                        job_item["region"],
                        job_item["vehicleType"],
                        f"Table fetch returned no data after {job_item['timeout_seconds'] / 60} minutes timeout",
                    )
                    timed_out_job_ids.add(job_item["id"])

            if timed_out_job_ids:
                pending_jobs = [
                    item for item in pending_jobs if item["id"] not in timed_out_job_ids
                ]

            if pending_jobs:
                time.sleep(3)
            continue

        matched_job_ids = set()
        clicked_job_id = None

        for i, elem in enumerate(elementsDest):
            dest_text = elem.text.strip()
            parts = [segment.strip() for segment in dest_text.split('-')]
            dest_one_customer = parts[0] if len(parts) > 0 else ''
            dest_two_customer = parts[1] if len(parts) > 1 else ''
            dest_three_customer = parts[2] if len(parts) > 2 else ''

            region_text = elementsRegion[i].text.strip() if i < len(elementsRegion) else "N/A"
            vehicle_text = elementsVehicle[i].text.strip() if i < len(elementsVehicle) else "N/A"
            select_text = elementsSelect[i].text.strip() if i < len(elementsSelect) else "N/A"
            print(
                f"Row {i}: Dest='{dest_text}', Region='{region_text}', Vehicle='{vehicle_text}', Select='{select_text}'",
                flush=True,
            )

            for job_item in pending_jobs:
                if job_item["id"] in matched_job_ids:
                    continue

                if (
                    dest_one_customer == (job_item["startDestination"] or '')
                    and dest_two_customer == (job_item["secondDestination"] or '')
                    and dest_three_customer == (job_item["thirdDestination"] or '')
                    and vehicle_text == (job_item["vehicleType"] or '')
                    and region_text == (job_item["region"] or '')
                ):
                    print(
                        f"--> Match found for job #{job_item['id']} at row {i} with exact destination: "
                        f"{dest_one_customer}-{dest_two_customer}-{dest_three_customer} "
                        f"AND vehicle: {vehicle_text} AND region: {region_text}",
                        flush=True,
                    )

                    if i < len(elementsSelect):
                        try:
                            elementsSelect[i].mouse_click()
                            clicked_job_id = job_item["id"]
                            print(f"Clicked select for job #{job_item['id']} at row {i}", flush=True)
                            sb.sleep(3)
                            sb.wait_for_element('button[data-v-50b69d50] span:contains("แข่งขันรับงาน")', timeout=15)
                            sb.sleep(5)
                            sb.mouse_click('button[data-v-50b69d50] span:contains("แข่งขันรับงาน")')
                            send_result(job_item["id"], "completed", job_item["region"], job_item["vehicleType"], f"{dest_text}")
                        except Exception as e:
                            print(f"Failed to click select for job #{job_item['id']} at row {i}: {e}", flush=True)
                            send_result(job_item["id"], "failed", job_item["region"], job_item["vehicleType"], f"{dest_text}")
                    else:
                        print(f"No select element for row {i} while processing job #{job_item['id']}", flush=True)
                        send_result(
                            job_item["id"],
                            "failed",
                            job_item["region"],
                            job_item["vehicleType"],
                            "No selectable action for matched row",
                        )

                    matched_job_ids.add(job_item["id"])

                    if clicked_job_id is not None:
                        break

            if clicked_job_id is not None:
                break

        if matched_job_ids:
            pending_jobs = [item for item in pending_jobs if item["id"] not in matched_job_ids]

        if clicked_job_id is not None and pending_jobs:
            pause_other_jobs_until = time.time() + pause_after_click_seconds
            print(
                f"[TurboManualTask] Job #{clicked_job_id} clicked. Pausing remaining {len(pending_jobs)} task(s) for {pause_after_click_seconds / 60:.2f} minute(s).",
                flush=True,
            )
            continue

        current_time = time.time()
        timed_out_job_ids = set()
        for job_item in pending_jobs:
            elapsed_seconds = current_time - job_item["started_at"]
            if elapsed_seconds >= job_item["timeout_seconds"]:
                print(
                    f"✗ No match found for job #{job_item['id']} after {job_item['timeout_seconds']} seconds timeout",
                    flush=True,
                )
                send_result(
                    job_item["id"],
                    "failed",
                    job_item["region"],
                    job_item["vehicleType"],
                    f"No match found after {job_item['timeout_seconds'] / 60} minutes timeout",
                )
                timed_out_job_ids.add(job_item["id"])

        if timed_out_job_ids:
            pending_jobs = [item for item in pending_jobs if item["id"] not in timed_out_job_ids]

        if pending_jobs:
            print(
                f"No match found yet for {len(pending_jobs)} job(s). Waiting 3 seconds before refetching...",
                flush=True,
            )
            time.sleep(3)


def turbo_get_tables(time):
    global sb
    try:
        elementsDest = sb.find_elements('td[class*="el-table_1_column_2"]', timeout=time)
        elementsRegion = sb.find_elements('td[class*="el-table_1_column_4"]', timeout=time)
        elementsVehicle = sb.find_elements('td[class*="el-table_1_column_5"]', timeout=time)
        elementsSelect = sb.find_elements('td[class*="el-table_1_column_13"] span', timeout=time)
        return elementsDest, elementsRegion, elementsVehicle, elementsSelect
    except TimeoutException as e:
        fail_msg = f"FAIL: Timed out waiting for table columns: {e}"
        print(fail_msg, flush=True)
        return [], [], [], []
    except Exception as e:
        fail_msg = f"FAIL: Error while fetching table columns: {e}"
        print(fail_msg, flush=True)
        return [], [], [], []


def send_result(job_id, status, region="", vehicle="", message=""):
    result = json.dumps({
        "type": "task_result",
        "id": job_id,
        "status": status,
        "region": region,
        "vehicle": vehicle,
        "message": message,
    })
    print(result, flush=True)


def listen_for_commands():
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

    cmd_thread = threading.Thread(target=listen_for_commands, daemon=True)
    cmd_thread.start()

try:
    while True:
        time.sleep(2)
        try:
            if sb is None or sb.driver is None:
                raise Exception("Browser reference lost")
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
