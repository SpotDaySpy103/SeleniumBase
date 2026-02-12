import sys
import time
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
    accountID = 'input[placeholder="Account ID"]'
    accountPW = 'input[placeholder="Password"]'
    sb.type(accountID, username)
    sb.type(accountPW, password)
    sb.click('button:contains(" Login ")')
    sb.sleep(2)
    sb.click('label:contains("TH")')

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: cdp_turbobot.py <username> <password>")
        sys.exit(1)
    username = sys.argv[1]
    password = sys.argv[2]
    turbo_login(username, password)

try:
	while True:
		time.sleep(1)
		try:
			# Ping the browser; if it's closed, this will raise.
			_ = sb.get_title()
		except Exception:
			print("Browser window closed. Exiting...")
			break
finally:
	# Attempt to stop the CDP driver if still running.
	try:
		sb.driver.stop()
	except Exception:
		pass