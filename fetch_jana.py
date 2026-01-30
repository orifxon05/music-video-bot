import requests
try:
    r = requests.get("https://janatube.com", timeout=10)
    print(r.text[:2000])
except Exception as e:
    print(f"Error: {e}")
