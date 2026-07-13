import pandas as pd
import requests
from io import StringIO

url = "https://ja.wikipedia.org/wiki/日経平均株価"

headers = {
    "User-Agent": "Mozilla/5.0"
}

response = requests.get(
    url,
    headers=headers,
    timeout=30
)

tables = pd.read_html(
    StringIO(response.text)
)

print(f"表の数: {len(tables)}")

for i, table in enumerate(tables):
    print("\n====================")
    print(f"Table {i}")
    print(table.head())