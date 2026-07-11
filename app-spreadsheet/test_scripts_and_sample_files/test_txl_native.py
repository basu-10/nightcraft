#!/usr/bin/env python3
"""Test all TXL-native endpoints."""
import json
import urllib.request
import urllib.parse
import sys

BASE = "http://127.0.0.1:7029"

def req(method, path, data=None, headers=None):
    h = headers or {}
    d = json.dumps(data).encode() if data and isinstance(data, dict) else data
    if data and isinstance(data, dict):
        h.setdefault("Content-Type", "application/json")
    r = urllib.request.Request(BASE + path, data=d, headers=h, method=method)
    return json.loads(urllib.request.urlopen(r).read())

tests = 0
passed = 0

def check(name, ok, detail=""):
    global tests, passed
    tests += 1
    if ok:
        passed += 1
        print(f"  ✅ {name} {detail}")
    else:
        print(f"  ❌ {name} - FAILED {detail}")

print("=" * 60)
print("TXL-NATIVE API TESTS")
print("=" * 60)

# 1. Upload CSV -> auto-convert to TXL
print("\n1. UPLOAD CSV -> TXL conversion")
with open("uploads/timeline_export_2025-11-30_6.csv", "rb") as f:
    csv_data = f.read()
boundary = "----TestBoundary"
parts = (
    "--" + boundary + "\r\n"
    'Content-Disposition: form-data; name="file"; filename="testme.csv"\r\n'
    "Content-Type: text/csv\r\n\r\n"
).encode() + csv_data + ("\r\n--" + boundary + "--\r\n").encode()
r = json.loads(urllib.request.urlopen(urllib.request.Request(
    BASE + "/api/upload", data=parts,
    headers={"Content-Type": "multipart/form-data; boundary=" + boundary}
)).read())
check("Response has file_path", "file_path" in r, r["file_path"])
check("File is .txl", r["file_path"].endswith(".txl"))
check("Has sheets list", len(r.get("sheets", [])) > 0)
fp = r["file_path"]
fid = r["file_id"]

# 2. Load sheet data from TXL
print("\n2. SHEET LOADING from TXL")
sn = r["sheets"][0]
sr = req("GET", f"/api/sheet?file={urllib.parse.quote(fp)}&sheet={urllib.parse.quote(sn)}&file_id={fid}")
check("Sheet data returned", "sheet" in sr, f'rows={sr["sheet"]["rows"]} cols={sr["sheet"]["cols"]}')
check("Layout present", sr["layout"] is not None)

# 3. Save layout to TXL
print("\n3. LAYOUT persistence in TXL")
lr = req("POST", "/api/layout", {"file_path": fp, "sheet_name": sn, "state": {"column_widths": {"0": 200, "1": 150}, "sticky_row": 0, "header_rows": [0]}})
check("Layout saved", lr.get("success") is True)
with open(fp) as f:
    txl = json.load(f)
layout = txl["file"]["sheets"][0]["layout"]
check("Sticky row persisted", layout["sticky_row"] == 0)
check("Column widths persisted", layout["column_widths"].get("0") == 200)

# 4. Create linked filter
print("\n4. LINKED FILTER in TXL")
lr2 = req("POST", "/api/linked-sheet", {"file_path": fp, "source_sheet": sn, "display_name": "FilterTest", "filter_col": 0, "filter_op": "contains", "filter_val": "2025"})
check("Linked filter created", "id" in lr2)
with open(fp) as f:
    txl = json.load(f)
sheet_linked = txl["file"]["sheets"][0].get("linked_sheets", [])
check("Linked filter in sheet", len(sheet_linked) > 0, f'count={len(sheet_linked)}')

# 5. Export TXL
print("\n5. EXPORT TXL")
er = req("GET", f"/api/export/txl?file={urllib.parse.quote(fp)}")
check("Export has sheets", len(er["file"]["sheets"]) > 0)
check("Export has sheet linked_sheets", "linked_sheets" in er["file"]["sheets"][0])

# 6. Create new file
print("\n6. NEW FILE creation")
nr = req("POST", "/api/new", {"file_name": "TestNew.txl"})
check("New file is .txl", nr["file_path"].endswith(".txl"))
check("New file has Sheet1", "Sheet1" in nr.get("sheets", []))

# 7. Recent files
print("\n7. RECENT FILES")
rr = req("GET", "/api/recent")
check("Recent files returned", len(rr.get("files", [])) > 0)

# 8. Sheet operations
print("\n8. SHEET OPERATIONS")
# Duplicate
dr = req("POST", "/api/sheet/duplicate", {"file_path": fp, "sheet_name": sn})
check("Sheet duplicated", dr.get("success") is True, f'new={dr.get("new_sheet")}')

# Create
cr = req("POST", "/api/sheet/create", {"file_path": fp})
check("Sheet created", cr.get("success") is True, f'new={cr.get("new_sheet")}')
new_sheet = cr["new_sheet"]

# Reorder
rr2 = req("POST", "/api/sheet/reorder", {"file_path": fp, "sheet_name": sn, "direction": "right"})
check("Sheet reordered", rr2.get("success") is True)

# Delete
delr = req("POST", "/api/sheet/delete", {"file_path": fp, "sheet_name": new_sheet})
check("Sheet deleted", delr.get("success") is True)

# 9. File metadata
print("\n9. FILE METADATA")
fm = req("GET", f"/api/file-metadata?file_id={fid}&file={urllib.parse.quote(fp)}")
check("Meta has original_name", "original_name" in fm)
check("Meta has sheets", len(fm.get("sheets", [])) > 0)

# 10. Open path
print("\n10. OPEN PATH")
op = req("POST", "/api/open-path", {"path": fp})
check("Open path works", op.get("file_id") == fid, f'fid={op.get("file_id")}')

# 11. Linked sheet data
print("\n11. LINKED SHEET DATA")
lsr = req("GET", f"/api/linked-sheet-data?linked_id={lr2['id']}&file={urllib.parse.quote(fp)}")
check("Linked data returned", "data" in lsr, f'rows={lsr.get("rows")}')

# 12. Filter preview
print("\n12. FILTER PREVIEW")
fpr = req("POST", "/api/filter-preview", {"file_path": fp, "sheet_name": sn, "filter_col": 0, "filter_op": "contains", "filter_val": "2025", "preserve_headers": False, "header_rows": []})
check("Filter preview returned", "total_matches" in fpr)

print(f"\n{'='*60}")
print(f"RESULTS: {passed}/{tests} tests passed ✅")
if passed == tests:
    print("ALL TESTS PASSED!")
else:
    print(f"{tests - passed} TESTS FAILED ❌")
    sys.exit(1)