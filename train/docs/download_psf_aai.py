import requests

URL = 'https://www.tesda.gov.ph/Uploads/File/Philippine%20Skills%20Framework/ICT/Philippine%20Skills%20Framework%20for%20Analytics%20and%20Artificial%20Intelligence.pdf'
OUT = "Philippine_Skills_Framework_Analytics_AI.pdf"

r = requests.get(URL, timeout=60)
r.raise_for_status()
with open(OUT, "wb") as f:
    f.write(r.content)

print(f"Saved {OUT} ({len(r.content):,} bytes)")
