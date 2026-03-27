"""Quick validation script — run against already-running server."""
import requests

url = "http://localhost:8001/analyze"
with open("../killerTest.csv", "rb") as f:
    r = requests.post(url, files={"file": ("killerTest.csv", f, "text/csv")})

print("status:", r.status_code)
d = r.json()
print("response keys:", list(d.keys()))
print("suspicious count:", len(d["suspicious_accounts"]))
print("ring count:", len(d["fraud_rings"]))
print("summary:", d["summary"])

flagged_ids = [a["account_id"] for a in d["suspicious_accounts"]]

print("\nTop 10 suspicious:")
for a in d["suspicious_accounts"][:10]:
    print(f"  {a['account_id']:25s}  score={a['suspicion_score']}  patterns={a['detected_patterns']}")

print()
print("Amazon flagged:", any("AMAZON" in x.upper() for x in flagged_ids))
print("Payroll/Company flagged:", any("PAYROLL" in x.upper() or "COMPANY" in x.upper() for x in flagged_ids))
print("Employee flagged:", any("EMP" in x.upper() for x in flagged_ids))
print("graph in response:", "graph" in d)
first_ring = d["fraud_rings"][0] if d["fraud_rings"] else {}
print("confidence in rings:", "confidence" in first_ring)
print("network_statistics in summary:", "network_statistics" in d["summary"])

# Also test detail=true returns graph
r2 = requests.post(url + "?detail=true", files={"file": ("killerTest.csv", open("../killerTest.csv", "rb"), "text/csv")})
d2 = r2.json()
print("\n--- detail=true ---")
print("graph in response:", "graph" in d2)
print("parse_stats in response:", "parse_stats" in d2)
