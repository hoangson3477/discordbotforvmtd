#!/usr/bin/env python3
"""Script để encode file JSON mới và hiển thị"""
import base64
import json
import sys

if len(sys.argv) < 2:
    print("Usage: python update_railway.py <path_to_new_json_file>")
    sys.exit(1)

json_file = sys.argv[1]

with open(json_file, 'r') as f:
    creds = json.load(f)

creds_json = json.dumps(creds)
creds_b64 = base64.b64encode(creds_json.encode()).decode()

print("\n" + "="*70)
print("COPY DÒNG NÀY VÀO RAILWAY:")
print("="*70)
print(f"\nGOOGLE_SHEET_CREDENTIALS_B64={creds_b64}\n")
print("="*70)
print("\nLưu ý:")
print("1. Vào Railway Dashboard → Variables")
print("2. Xóa biến GOOGLE_SHEET_CREDENTIALS_B64 cũ")
print("3. Tạo biến mới với value ở trên")
print("4. Redeploy")
