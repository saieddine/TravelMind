import os
from dotenv import load_dotenv
from openai import OpenAI

# Load the API key
load_dotenv()

# Connect to OpenRouter
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

# Send a test request with a larger token budget
response = client.chat.completions.create(
    model="nvidia/nemotron-3.5-lightning:free",
    messages=[
        {
            "role": "user",
            "content": "Say hello in one short sentence. Do not explain your reasoning."
        }
    ],
    max_tokens=2000,
)

# Display the final answer
message = response.choices[0].message

print("Finish reason:", response.choices[0].finish_reason)
print("Answer:", repr(message.content))
print("Usage:", response.usage)