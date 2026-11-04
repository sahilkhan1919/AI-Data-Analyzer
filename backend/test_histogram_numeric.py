import requests
import json
from pathlib import Path

API = "http://127.0.0.1:5000"

csv_content = "Category,Value\nA,10\nB,20\nC,30\nA,5\nB,15\n"

p = Path("test_sample2.csv")
p.write_text(csv_content)

with open(p, "rb") as f:
    resp = requests.post(f"{API}/upload", files={"file": f})

data = resp.json()
dataset_id = data.get("dataset_id")

payload = {
    "dataset_id": dataset_id,
    "chart_type": "Histogram",
    "x_axis": "Value",
    "y_axis": ""
}

r = requests.post(f"{API}/chart-data", json=payload)
print("/chart-data histogram numeric ->", r.status_code)
print(json.dumps(r.json(), indent=2))
