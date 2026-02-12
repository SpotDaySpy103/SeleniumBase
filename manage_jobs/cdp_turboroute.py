from seleniumbase import sb_cdp
from selenium.common.exceptions import TimeoutException
from flask import Flask, request, jsonify
from flask_cors import CORS
import time

app = Flask(__name__)
CORS(app)
# Global browser instance and job store
sb = None
jobs = {}
jobs_queue = []
url = "https://th.turboroute.ai/#/login?redirect=%2Fgrab-single%2Fsingle-hall"
urlMock = "http://127.0.0.1:5500/SeleniumBase/manage_jobs/mockTable.html"

# Helper to normalize vehicle strings for exact comparison
def _norm_vehicle(s: str) -> str:
	if s is None:
		return ""
	# Uppercase, strip spaces, remove non-alphanumerics
	s = s.strip().upper()
	return "".join(ch for ch in s if ch.isalnum())

@app.route('/api/turboLogin', methods=['POST'])
def turbo_login():
	global sb
	try:
		data = request.get_json()
		username = data.get('username')
		password = data.get('password')

		print(f"Received credentials for: {username} , {password}")
		# check if browser is started
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

		return jsonify({
			'status': 'Logged In Turbo',
			'message': 'Login attempted',
			'browserStatus': 'running',
			'username': username
		}), 200
	
	except Exception as e:
		print(f"Error in turbo_login: {str(e)}")
		return jsonify({'error': str(e)}), 500
	
@app.route('/api/turboManage', methods=['POST'])
def turbo_manage():
	global sb, jobs
	try:
		data = request.get_json()
		jobNumber = data.get('jobNumber', str(int(time.time())))
		region = data.get('region')
		vehicleType = data.get('vehicleType')
		startDest = data.get('startDest')

		if sb is None:
			return jsonify({'error': 'Browser not initialized. Login first.'}), 400

		# Initialize job as pending
		jobs[jobNumber] = {
			'status': 'PENDING',
			'region': region,
			'vehicleType': vehicleType,
			'startDest': startDest,
			'startTime': time.time(),
			'endTime': None,
		}

		# Queue this job and wait for turn (simple in-memory FIFO)
		jobs_queue.append(jobNumber)
		print(f"Queued job {jobNumber}. Queue: {jobs_queue}")
		while jobs_queue and jobs_queue[0] != jobNumber:
			time.sleep(0.2)
		print(f"Processing job {jobNumber}")

		# Get all relevant elements with retry logic
		print(f'Fetching table data for region: {region}, vehicleType: {vehicleType}, startDest: {startDest}')

		match_found = False

		# Set timeout for search rows
		search_timeout = 60  # seconds
		search_start_time = time.time()

		while not match_found and (time.time() - search_start_time) < search_timeout:
			# print(f'current time: {time.time()}, start time: {search_start_time}, search timeout: {search_timeout}')
			# Fetch table elements
			tables_result = turbo_get_tables(jobNumber, region, vehicleType, startDest)
			if not isinstance(tables_result, tuple):
				return tables_result
			elementsDest, elementsVehicle, elementsSelect = tables_result

			print(f"Found {len(elementsDest)} elements in column 2")
			print(f"Found {len(elementsVehicle)} elements in column 5")
			print(f"Found {len(elementsSelect)} elements in column 13")

			# Search through all rows
			for i, element in enumerate(elementsDest):
				text = element.text.strip()
				print(f"Row {i+1}: {text}")

				# 1. Separate words between hyphens
				parts = text.split('-')
				print(f"  Split parts: {parts}")

				# 2. Store in order (handle cases with different numbers of parts)
				destOneCus = parts[0] if len(parts) > 0 else ''
				destTwoCus = parts[1] if len(parts) > 1 else ''
				destThreeCus = parts[2] if len(parts) > 2 else ''
				print(f"  Assigned parts: [{destOneCus}], [{destTwoCus}], [{destThreeCus}]")

				# Get vehicle type from elementsVehicle at same index
				vehicle = ''
				if i < len(elementsVehicle):
					vehicle = elementsVehicle[i].text.strip()
					print(f"  Vehicle Type: {vehicle}")

				# 3. Check matches
				destMatch = startDest in [destOneCus]
				vt_norm = _norm_vehicle(vehicleType)
				v_norm = _norm_vehicle(vehicle)
				vehicleMatch = (v_norm == vt_norm) if v_norm else False
				print(f"  Destination Match ('{startDest}'): {destMatch}")
				print(f"  Vehicle Match exact ({vt_norm} == {v_norm}): {vehicleMatch}")

				if destMatch and vehicleMatch:
					print(f"✓ MATCH FOUND! Both destination and vehicle match in row {i+1}: {text}")
					print(f"  Destination: [{destOneCus}], [{destTwoCus}], [{destThreeCus}]")
					print(f"  Vehicle Type: {vehicle}")
					sb.sleep(0.5)
					try:
						# Find and click the span containing Thai text within the select column
						print(f"finding แข่งขันรับงาน")
						elementsSelect[i].mouse_click()
						sb.sleep(3)
						# sb.wait_for_element_absent('button[disabled] span:contains("แข่งขันรับงาน")')
						# sb.highlight_overlay('div button[data-v-50b69d50] span:contains("แข่งขันรับงาน")')
						# sb.mouse_click('div button[data-v-50b69d50] span:contains("แข่งขันรับงาน")')
						print(f"✓ Clicked แข่งขันรับงาน button at row {i+1}")
						match_found = True
						jobs[jobNumber]['status'] = 'SUCCESS'
						jobs[jobNumber]['endTime'] = time.time()
						break
					except Exception as e:
						print(f"✗ Click failed: {e}")
				elif destMatch:
					print(f"✓ Destination matched but vehicle type doesn't match")
				elif vehicleMatch:
					print(f"✓ Vehicle type matched but destination doesn't match")
				else:
					print(f"  No match")
			
			# If not found in this iteration, wait before refetching
			if not match_found:
				elapsed = time.time() - search_start_time
				remaining = search_timeout - elapsed
				if remaining > 0:
					print(f"No match found. Waiting 2 seconds before refetching... ({remaining:.1f}s remaining)")
					time.sleep(2)

		# After timeout
		if not match_found:
			print(f"✗ No match found after {search_timeout} seconds timeout")
			jobs[jobNumber]['status'] = 'NOT_FOUND'
			jobs[jobNumber]['endTime'] = time.time()
			
		# Job finished; remove from queue
		if jobs_queue and jobs_queue[0] == jobNumber:
			jobs_queue.pop(0)
		print(f"Completed job {jobNumber}. Queue: {jobs_queue}")
		
		# Cleanup old jobs (keep last 100)
		if len(jobs) > 100:
			oldest = sorted(jobs.items(), key=lambda x: x[1].get('startTime', 0))[:50]
			for job_num, _ in oldest:
				del jobs[job_num]
			print(f"Cleaned up {len(oldest)} old jobs")

		return jsonify({
					'status': jobs[jobNumber]['status'],
					'message': 'Match found and clicked' if match_found else 'No matching row found',
					'browserStatus': 'running',
					'region': region,
					'vehicleType': vehicleType,
					'startDest': startDest,
					'jobNumber': jobNumber,
					'job': jobs[jobNumber]
				}), 200
	
	except Exception as e:
		print(f"Error in turbo_manage: {str(e)}")
		# Ensure queue advances if current job fails
		if jobs_queue and jobs_queue[0] == jobNumber:
			jobs_queue.pop(0)
		return jsonify({'error': str(e)}), 500

def turbo_get_tables(jobNumber,region,vehicleType,startDest):
	global sb,jobs
	try:
			elementsDest = sb.find_elements('td[class*="el-table_1_column_2"]', timeout=30)
			elementsVehicle = sb.find_elements('td[class*="el-table_1_column_5"]', timeout=30)
			elementsSelect = sb.find_elements('td[class*="el-table_1_column_13"]', timeout=30) #'td[class*="el-table_1_column_13"] span'
			return elementsDest, elementsVehicle, elementsSelect
	except TimeoutException as e:
		fail_msg = f"FAIL: Timed out waiting for table columns: {e}"
		print(fail_msg)
		jobs[jobNumber]['status'] = 'NOT_FOUND'
		jobs[jobNumber]['endTime'] = time.time()
		return jsonify({
				'status': jobs[jobNumber]['status'],
				'message': fail_msg,
				'browserStatus': 'running',
				'region': region,
				'vehicleType': vehicleType,
				'startDest': startDest,
				'jobNumber': jobNumber,
				'job': jobs[jobNumber]
			}), 504
	except Exception as e:
		fail_msg = f"FAIL: Error while fetching table columns: {e}"
		print(fail_msg)
		jobs[jobNumber]['status'] = 'NOT_FOUND'
		jobs[jobNumber]['endTime'] = time.time()
		return jsonify({
				'status': jobs[jobNumber]['status'],
				'message': fail_msg,
				'browserStatus': 'running',
				'region': region,
				'vehicleType': vehicleType,
				'startDest': startDest,
				'jobNumber': jobNumber,
				'job': jobs[jobNumber]
			}), 500

@app.route('/api/jobs', methods=['GET'])
def get_jobs():
	"""Return all tracked jobs and their statuses."""
	global jobs
	try:
		# Convert jobs dict to array for easier consumption
		job_list = []
		for job_num, info in jobs.items():
			item = {
				'jobNumber': job_num,
				**info,
			}
			job_list.append(item)
		# Sort by startTime descending if present
		job_list.sort(key=lambda j: j.get('startTime') or 0, reverse=True)
		return jsonify({'jobs': job_list}), 200
	except Exception as e:
		print(f"Error in get_jobs: {str(e)}")
		return jsonify({'error': str(e)}), 500

@app.route('/api/status', methods=['GET'])
def get_status():
	"""Check browser status."""
	global sb
	try:
		browser_running = sb is not None
		return jsonify({
			'browserRunning': browser_running,
			'queueLength': len(jobs_queue),
			'totalJobs': len(jobs)
		}), 200
	except Exception as e:
		print(f"Error in get_status: {str(e)}")
		return jsonify({'error': str(e)}), 500

@app.route('/api/cleanup', methods=['POST'])
def cleanup():
	"""Cleanup jobs only."""
	global jobs
	try:
		jobs.clear()
		return jsonify({'status': 'cleaned', 'clearedJobs': True}), 200
	except Exception as e:
		print(f"Error in cleanup: {str(e)}")
		return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
	#Run Flask server (single-threaded for browser safety)
	app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False, threaded=False)