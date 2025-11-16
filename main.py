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
STANDINGS_JSON_URL = f"http://{PC_IP}:{PC_PORT}/standings.json"
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
    print(f"Connected to Wi-Fi. ESP32 IP: {ip}")
    return ip

# === Fetch raw JSON from PC ===
def fetch_raw_json(max_retries=3, delay=2):
    for attempt in range(max_retries):
        try:
            print("Fetching:", STANDINGS_JSON_URL)
            response = requests.get(STANDINGS_JSON_URL)
            text = response.text
            response.close()
            return text
        except Exception as e:
            print(f"Fetch attempt {attempt+1} failed:", e)
            time.sleep(delay)
    return None

# === Parse JSON into dict ===
def load_data(raw_text, truth=False):
    if not raw_text:
        return {"East": [], "West": []} if truth else {
            "Can": {"East": [], "West": []},
            "Marlon": {"East": [], "West": []},
            "Ole": {"East": [], "West": []}
        }
    try:
        data = json.loads(raw_text)
        if truth:
            for key in ["East", "West"]:
                if key not in data: data[key] = []
        else:
            for user in ["Can", "Marlon", "Ole"]:
                if user not in data:
                    data[user] = {"East": [], "West": []}
                else:
                    if "East" not in data[user]: data[user]["East"] = []
                    if "West" not in data[user]: data[user]["West"] = []
        return data
    except Exception as e:
        print("Error parsing JSON:", e)
        return {"East": [], "West": []} if truth else {
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
        print("Template load error:", e)
        return "<html><body><p>Template error</p></body></html>"

# === Build table rows for truth + predictions (with games_behind) ===
def build_table_html(truth_data, predictions_data, conf):
    html_rows = {}

    # --- Truth table ---
    truth_html = ""
    for i, team in enumerate(truth_data[conf]):
        truth_html += (
            f"<tr>"
            f"<td>{i+1}</td>"
            f"<td>{team['team']}</td>"
            f"<td class='win'>{team['wins']}</td>"
            f"<td class='loss'>{team['losses']}</td>"
            f"<td>{team['games_behind']}</td>"
            f"</tr>"
        )
    html_rows[f"truth-{conf.lower()}"] = truth_html

    # --- Prediction tables ---
    for user in ["Can", "Marlon", "Ole"]:
        pred_html = ""
        predicted_list = predictions_data.get(user, {}).get(conf, [])
        for team in predicted_list:
            pred_html += f"<tr><td>{team['seed']}</td><td>{team['team']}</td></tr>"
        html_rows[f"{user.lower()}-{conf.lower()}"] = pred_html

    return html_rows

# === Start web server ===
def start_web_server(ip):
    template = load_template()

    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('0.0.0.0', WEB_PORT))
    s.listen(5)
    print(f"Web server running on http://{ip}:{WEB_PORT}")

    while True:
        cl, addr = s.accept()
        try:
            request = cl.recv(1024).decode()

            # --- Fetch truth from PC ---
            raw_truth = fetch_raw_json()
            truth_data = load_data(raw_truth, truth=True)

            # --- Load predictions from local file ---
            try:
                with open("predictions.json") as f:
                    predictions_raw = json.load(f)
                predictions_data = load_data(json.dumps(predictions_raw), truth=False)
            except Exception:
                predictions_data = {
                    "Can": {"East": [], "West": []},
                    "Marlon": {"East": [], "West": []},
                    "Ole": {"East": [], "West": []}
                }

            # --- Combined JSON for /standings.json ---
            combined_data = truth_data.copy()
            combined_data.update(predictions_data)

            if "GET /standings.json" in request:
                cl.send(b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n")
                cl.send(json.dumps(combined_data))
            else:
                html = template
                for conf in ["East", "West"]:
                    rows = build_table_html(truth_data, predictions_data, conf)
                    for key, v in rows.items():
                        html = html.replace(f"{{{{{key}}}}}", v)
                cl.send(b"HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n")
                cl.send(html.encode())

        except Exception as e:
            print("Error handling request:", e)
        finally:
            cl.close()

# === Main ===
if __name__ == "__main__":
    ip = connect_wifi()
    start_web_server(ip)

