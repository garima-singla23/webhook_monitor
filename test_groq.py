from dotenv import load_dotenv
import os
from groq import Groq

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")

print("PREFIX:", api_key[:12])
print("LENGTH:", len(api_key))

client = Groq(api_key=api_key)

response = client.chat.completions.create(
    model="llama-3.1-8b-instant",
    messages=[
        {"role": "user", "content": "Say hello in one sentence"}
    ]
)

print(response.choices[0].message.content)