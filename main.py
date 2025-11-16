import network
import urequests as requests
import ujson as json
import socket
import time
import os

# === Load config ===
CONFIG_FILE = "config.json"

try:
    with open(CONFIG_FILE) as f:
        config = json.load(f)
except Exception as e:
    print("Failed to load config:", e)
    config = {}

SSID = config.get("wifi_ssid", "")
PASSWORD = config.get("wifi_password", "")
PC_IP = config.get("pc_ip", "")
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

# === Fetch raw JSON from PC safely ===
def fetch_raw_json(max_retries=3, delay=2):
    for attempt in range(max_retries):
        try:
            print("Fetching:", STANDINGS_JSON_URL)
            response = requests.get(STANDINGS_JSON_URL)
            text = response.text
            response.close()
            if not text.strip():
                return None
            return text
        except Exception as e:
            print(f"Fetch attempt {attempt+1} failed:", e)
            time.sleep(delay)
    return None

# === Load JSON with defaults ===
def load_data(raw_text, truth=False):
    if not raw_text:
        if truth:
            return {"East": [], "West": []}
        else:
            return {u: {"East": [], "West": []} for u in ["Can", "Marlon", "Ole"]}
    try:
        data = json.loads(raw_text)
        if truth:
            for k in ["East", "West"]:
                if k not in data or not isinstance(data[k], list):
                    data[k] = []
        else:
            for user in ["Can", "Marlon", "Ole"]:
                if user not in data or not isinstance(data[user], dict):
                    data[user] = {"East": [], "West": []}
                else:
                    if "East" not in data[user] or not isinstance(data[user]["East"], list):
                        data[user]["East"] = []
                    if "West" not in data[user] or not isinstance(data[user]["West"], list):
                        data[user]["West"] = []
        return data
    except Exception as e:
        print("Error parsing JSON:", e)
        return {"East": [], "West": []} if truth else {u: {"East": [], "West": []} for u in ["Can", "Marlon", "Ole"]}

# === Load predictions safely ===
def load_predictions():
    try:
        with open("predictions.json") as f:
            raw = f.read()
            return load_data(raw, truth=False)
    except Exception:
        return {u: {"East": [], "West": []} for u in ["Can", "Marlon", "Ole"]}

# === Load HTML template ===
def load_template():
    try:
        with open("template.html") as f:
            return f.read()
    except Exception as e:
        print("Template load error:", e)
        return "<html><body><p>Template error</p></body></html>"

# === Build table rows for truth + predictions ===
def build_table_html(truth_data, predictions_data, conf):
    html_rows = {}

    # --- Truth table ---
    truth_html = ""
    if truth_data.get(conf):
        for i, team in enumerate(truth_data[conf]):
            truth_html += (
                f"<tr>"
                f"<td>{i+1}</td>"
                f"<td>{team.get('team','')}</td>"
                f"<td class='win'>{team.get('wins','')}</td>"
                f"<td class='loss'>{team.get('losses','')}</td>"
                f"<td>{team.get('games_behind','')}</td>"
                f"</tr>"
            )
    else:
        truth_html = "<tr><td colspan='5'>No data available</td></tr>"

    html_rows[f"truth-{conf.lower()}"] = truth_html

    # --- Prediction tables ---
    for user in ["Can", "Marlon", "Ole"]:
        pred_html = ""
        predicted_list = predictions_data.get(user, {}).get(conf, [])
        if predicted_list:
            for team in predicted_list:
                pred_html += f"<tr><td>{team.get('seed','')}</td><td>{team.get('team','')}</td></tr>"
        else:
            pred_html = "<tr><td colspan='2'>No predictions</td></tr>"
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

            # --- Fetch truth and predictions safely ---
            raw_truth = fetch_raw_json()
            truth_data = load_data(raw_truth, truth=True)
            predictions_data = load_predictions()

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

def main():
    ip = connect_wifi()
    start_web_server(ip)    

# === Main ===
if __name__ == "__main__":
    main()
