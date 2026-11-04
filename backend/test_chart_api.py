import requests
import json
from pathlib import Path

API = "http://127.0.0.1:5000"

csv_content = "Category,Value\nA,10\nB,20\nC,30\nA,5\nB,15\n"

p = Path("test_sample.csv")
p.write_text(csv_content)

with open(p, "rb") as f:
    resp = requests.post(f"{API}/upload", files={"file": f})

print("/upload status:", resp.status_code)
print(resp.text)

data = resp.json()
dataset_id = data.get("dataset_id")

chart_types = ["Bar", "Line", "Pie", "Scatter", "Histogram"]

for ct in chart_types:
    payload = {
        "dataset_id": dataset_id,
        "chart_type": ct,
        "x_axis": "Category",
        "y_axis": "Value"
    }
    r = requests.post(f"{API}/chart-data", json=payload)
    print(f"\n/chart-data for {ct} -> status {r.status_code}")
    try:
        print(json.dumps(r.json(), indent=2))
    except Exception as e:
        print("Non-JSON response", r.text)
