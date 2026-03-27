"""
Integration test — verifies all detection patterns, JSON format, and scoring.
Run:  python backend/test_integration.py
"""
import csv
import json
import os
import subprocess
import tempfile
import sys

# ── Build test CSV covering all 3 patterns + a legitimate merchant trap ────────
rows = [["transaction_id","sender_id","receiver_id","amount","timestamp"]]

# Pattern 1: Cycle (A -> B -> C -> A)
rows += [
    ["CYC_01","ACC_A","ACC_B","500","2024-01-01 10:00:00"],
    ["CYC_02","ACC_B","ACC_C","490","2024-01-01 11:00:00"],
    ["CYC_03","ACC_C","ACC_A","480","2024-01-01 12:00:00"],
]

# Pattern 2: Fan-in (12 unique senders -> HUB_IN within 72h)
for i in range(12):
    rows.append([f"FI_{i:02d}", f"SENDER_{i:02d}", "HUB_IN", str(100 + i), "2024-01-02 10:00:00"])

# Pattern 3: Fan-out (HUB_OUT -> 12 unique receivers within 72h)
for i in range(12):
    rows.append([f"FO_{i:02d}", "HUB_OUT", f"RECEIVER_{i:02d}", str(200 + i), "2024-01-03 14:00:00"])

# Pattern 4: Shell chain — S_SRC -> SHELL_1 -> SHELL_2 -> S_DST
# SHELL_1 and SHELL_2 have <=3 total transactions (qualifying them as shells)
# S_SRC and S_DST are non-shell (they need >3 tx to NOT be shells themselves)
for i in range(4):
    rows.append([f"S_SRC_{i}", "S_SRC", f"EXTRA_SRC_{i}", str(50), f"2024-01-04 0{i}:00:00"])
for i in range(4):
    rows.append([f"S_DST_{i}", f"EXTRA_DST_{i}", "S_DST", str(50), f"2024-01-04 0{i}:00:00"])
rows += [
    ["SHELL_01","S_SRC","SHELL_1","300","2024-01-05 09:00:00"],
    ["SHELL_02","SHELL_1","SHELL_2","290","2024-01-05 10:00:00"],
    ["SHELL_03","SHELL_2","S_DST","280","2024-01-05 11:00:00"],
]

# Write to temp file
tmp = tempfile.NamedTemporaryFile(suffix='.csv', delete=False, mode='w', newline='',
                                  dir=os.path.dirname(os.path.abspath(__file__)))
csv.writer(tmp).writerows(rows)
tmp.close()

# Call the API
result = subprocess.run(
    ["curl", "-s", "-F", f"file=@{tmp.name};type=text/csv", "http://localhost:8000/analyze"],
    capture_output=True, text=True, timeout=30
)
os.unlink(tmp.name)

if result.returncode != 0:
    print("CURL FAILED:", result.stderr)
    sys.exit(1)

data = json.loads(result.stdout)

# ── Assertions ──────────────────────────────────────────────────────────────────
errors = []

def check(cond, msg):
    if not cond:
        errors.append(msg)

# --- Top-level keys ---
for key in ["suspicious_accounts", "fraud_rings", "summary", "graph"]:
    check(key in data, f"Missing top-level key: {key}")

# --- Summary ---
s = data["summary"]
check("total_accounts_analyzed" in s, "summary missing total_accounts_analyzed")
check("suspicious_accounts_flagged" in s, "summary missing suspicious_accounts_flagged")
check("fraud_rings_detected" in s, "summary missing fraud_rings_detected")
check("processing_time_seconds" in s, "summary missing processing_time_seconds")
check(s["processing_time_seconds"] <= 30, f"Processing time {s['processing_time_seconds']}s > 30s")

# --- Fraud rings ---
rings = data["fraud_rings"]
ring_patterns = {r["pattern_type"] for r in rings}
check(any(p.startswith("cycle_length_") for p in ring_patterns), "No cycle ring detected")
check("fan_in" in ring_patterns, "No fan_in ring detected")
check("fan_out" in ring_patterns, "No fan_out ring detected")

for r in rings:
    for key in ["ring_id", "member_accounts", "pattern_type", "risk_score"]:
        check(key in r, f"Fraud ring {r.get('ring_id','?')} missing key: {key}")
    check(isinstance(r.get("risk_score"), (int, float)), f"risk_score not numeric in {r.get('ring_id')}")
    check(0 <= r.get("risk_score", -1) <= 100, f"risk_score out of range in {r.get('ring_id')}")

# --- Suspicious accounts ---
accs = data["suspicious_accounts"]
check(len(accs) > 0, "No suspicious accounts flagged")

for a in accs:
    for key in ["account_id", "suspicion_score", "detected_patterns", "ring_id"]:
        check(key in a, f"Account {a.get('account_id','?')} missing key: {key}")

# Sorted descending?
scores = [a["suspicion_score"] for a in accs]
check(scores == sorted(scores, reverse=True), "suspicious_accounts NOT sorted descending by score")

# Score range
for a in accs:
    check(0 <= a["suspicion_score"] <= 100, f"Score out of range for {a['account_id']}: {a['suspicion_score']}")

# Check cycle members flagged
cycle_members = {"ACC_A", "ACC_B", "ACC_C"}
flagged_ids = {a["account_id"] for a in accs}
for m in cycle_members:
    check(m in flagged_ids, f"Cycle member {m} not in suspicious_accounts")

# Check fan-in hub flagged
check("HUB_IN" in flagged_ids, "Fan-in hub HUB_IN not flagged")

# Check fan-out hub flagged
check("HUB_OUT" in flagged_ids, "Fan-out hub HUB_OUT not flagged")

# --- Graph ---
g = data["graph"]
check("nodes" in g, "graph missing nodes")
check("edges" in g, "graph missing edges")
check(len(g["nodes"]) > 0, "graph has no nodes")
check(len(g["edges"]) > 0, "graph has no edges")

# Graph nodes should have suspicious flag
suspicious_nodes = [n for n in g["nodes"] if n.get("suspicious")]
check(len(suspicious_nodes) > 0, "No suspicious nodes in graph")

# --- Parse stats ---
if "parse_stats" in data:
    ps = data["parse_stats"]
    check("valid_rows" in ps, "parse_stats missing valid_rows")
    check("warnings" in ps, "parse_stats missing warnings")

# --- Shell chain check ---
shell_detected = "shell_chain" in ring_patterns
if shell_detected:
    shell_ring = next(r for r in rings if r["pattern_type"] == "shell_chain")
    check("SHELL_1" in shell_ring["member_accounts"] or "SHELL_2" in shell_ring["member_accounts"],
           "Shell chain missing intermediary accounts")

# ── Report ──────────────────────────────────────────────────────────────────────
print("=" * 60)
print("INTEGRATION TEST RESULTS")
print("=" * 60)
print(f"Summary: {json.dumps(s, indent=2)}")
print(f"\nRings detected: {len(rings)}")
for r in rings:
    print(f"  {r['ring_id']}  {r['pattern_type']:16s}  members={len(r['member_accounts']):2d}  risk={r['risk_score']}")
print(f"\nSuspicious accounts: {len(accs)}")
for a in accs[:8]:
    print(f"  {a['account_id']:14s}  score={a['suspicion_score']:5.1f}  patterns={a['detected_patterns']}  ring={a['ring_id']}")
if len(accs) > 8:
    print(f"  ... and {len(accs) - 8} more")
print(f"\nGraph: {len(g['nodes'])} nodes, {len(g['edges'])} edges")
print(f"Shell chain detected: {shell_detected}")
if "parse_stats" in data:
    print(f"Parse stats: {data['parse_stats']}")

print(f"\n{'=' * 60}")
if errors:
    print(f"FAILURES ({len(errors)}):")
    for e in errors:
        print(f"  FAIL: {e}")
    sys.exit(1)
else:
    print("ALL CHECKS PASSED")
    sys.exit(0)
