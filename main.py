import network
import urequests as requests
import ujson as json
import socket
import time

# === Load config ===
with open("config.json") as f:
    config = json.load(f)

SSID = config["wifi_ssid"]
PASSWORD = config["wifi_password"]
PC_IP = config["pc_ip"]
PC_PORT = config.get("pc_port", 8000)
NBA_JSON_URL = f"http://{PC_IP}:{PC_PORT}/standings.json"
WEB_PORT = 80

# === Wi-Fi connection ===
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Connecting to Wi-Fi...")
        wlan.connect(SSID, PASSWORD)
        while not wlan.isconnected():
            time.sleep(1)
    ip = wlan.ifconfig()[0]
    print("Connected. IP:", ip)
    return ip

# === Fetch raw JSON from PC ===
def fetch_raw_json(max_retries=3, delay=2):
    for attempt in range(1, max_retries + 1):
        try:
            print(f"Fetching raw NBA JSON, attempt {attempt}...")
            response = requests.get(NBA_JSON_URL)
            text = response.text
            response.close()
            return text
        except OSError as e:
            print(f"Connection error on attempt {attempt}: {e}")
        except Exception as e:
            print(f"Unexpected error on attempt {attempt}: {e}")
        time.sleep(delay)
    print("Failed to fetch raw JSON after retries.")
    return None

# === Parse JSON into truth and predictions ===
def load_nba_data(raw_text):
    if not raw_text:
        return {
            "East": [], "West": [],
            "Can": {"East": [], "West": []},
            "Marlon": {"East": [], "West": []},
            "Ole": {"East": [], "West": []}
        }

    try:
        data = json.loads(raw_text)

        # Ensure all expected keys exist
        if "East" not in data: data["East"] = []
        if "West" not in data: data["West"] = []

        for user in ["Can", "Marlon", "Ole"]:
            if user not in data:
                data[user] = {"East": [], "West": []}
            else:
                if "East" not in data[user]: data[user]["East"] = []
                if "West" not in data[user]: data[user]["West"] = []

        print("Loaded JSON keys:", list(data.keys()))
        return data
    except ValueError as e:
        print("JSON parsing error:", e)
        return {
            "East": [], "West": [],
            "Can": {"East": [], "West": []},
            "Marlon": {"East": [], "West": []},
            "Ole": {"East": [], "West": []}
        }

# === Load HTML template ===
def load_template():
    try:
        with open("template.html") as f:
            return f.read()
    except Exception as e:
        print("Error loading template:", e)
        return "<html><body><p>Template error</p></body></html>"

# === Fill HTML template ===
def fill_template(template, data):
    def make_list(teams):
        return "".join(
            f"<li>Seed {i+1}: {t.get('team','')} ({t.get('wins','-')}-{t.get('losses','-')})</li>"
            for i, t in enumerate(teams)
        )
    east_html = make_list(data.get("East", []))
    west_html = make_list(data.get("West", []))
    
    html = template
    html = html.replace("{{east}}", east_html)
    html = html.replace("{{west}}", west_html)
    return html

# === Start web server on ESP ===
def start_web_server(ip):
    template = load_template()
    addr = socket.getaddrinfo('0.0.0.0', WEB_PORT)[0][-1]
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(5)
    print(f"Web server running on http://{ip}:{WEB_PORT}")

    while True:
        cl, addr = s.accept()
        try:
            request = cl.recv(1024).decode()
            
            # Fetch JSON only once per request
            raw_json = fetch_raw_json()
            data = load_nba_data(raw_json)

            if "GET /standings.json" in request:
                cl.send(b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n")
                cl.send(json.dumps(data))
            else:
                html = fill_template(template, data)
                cl.send(b"HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n")
                cl.send(html.encode('utf-8'))
        except Exception as e:
            print("Error handling request:", e)
        finally:
            cl.close()

# === Main ===
if __name__ == "__main__":
    ip = connect_wifi()
    start_web_server(ip)
