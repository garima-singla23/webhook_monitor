import os

key = os.getenv("GROQ_API_KEY")

print("KEY =", repr(key))

if key:
    print("PREFIX =", key[:12])
    print("LENGTH =", len(key))
else:
    print("KEY IS NONE")