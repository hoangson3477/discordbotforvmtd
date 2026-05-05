#!/usr/bin/env python3
"""Encode Google credentials file thành base64 để dùng trên Railway"""
import base64
import json

# Đọc file JSON credentials
with open('discordbotsheets-466304-0a64625eea26.json', 'r') as f:
    creds = json.load(f)

# Encode thành base64
creds_json = json.dumps(creds)
creds_b64 = base64.b64encode(creds_json.encode()).decode()

print("Copy dòng này vào Railway Environment Variable:")
print("\nGOOGLE_SHEET_CREDENTIALS_B64=\n")
print(creds_b64)
print("\n" + "="*60)
print("Lưu ý: Có thể paste vào biến env mà không cần dấu ngoặc")
