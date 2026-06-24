# test_redis.py
# Run this once to confirm your Upstash Redis
# connection works before testing Phase 3 features.
#
# Usage:
#   cd backend
#   python test_redis.py

import redis
import os
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("UPSTASH_REDIS_URL")

if not url:
    print(" UPSTASH_REDIS_URL not found in .env")
    exit(1)

print(f"Connecting to Redis...")

try:
    r = redis.from_url(url, decode_responses=True)

    r.set("test_key", "hello")
    value = r.get("test_key")
    print(f"GET test_key → {value}")

    r.delete("test_key")

    if value == "hello":
        print("Redis connection works!")
    else:
        print("Connected, but got unexpected value back")

except Exception as e:
    print(f"❌ Redis connection failed: {e}")