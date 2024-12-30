import base64
import requests
from dotenv import load_dotenv
import os

class ImageLLM:
    def __init__(self, image_path):
        load_dotenv()
        self.api_key = os.getenv('AI_KEY')
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        self.image_path = image_path

    def encode_image(self):
        with open(self.image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def transcribe_image(self):
        base64_image = self.encode_image()
        
        payload = {
            "model": "gpt-4o-mini",  # Updated model name
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Transcribe this:"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 300
        }

        response = requests.post("https://api.openai.com/v1/chat/completions", headers=self.headers, json=payload)
        message = response.json()
        
        if response.status_code != 200:
            print(f"Error: API request failed with status code {response.status_code}")
            print(f"Response: {message}")
            return None
        
        if 'choices' not in message:
            print(f"Error: Unexpected response format. Full response: {message}")
            return None
        
        return message['choices'][0]['message']['content']

def main():
    image_path = "WIN_20241011_10_46_46_Pro.jpg"
    image_llm = ImageLLM(image_path)
    transcription = image_llm.transcribe_image()
    if transcription:
        print("Transcription:", transcription)
    else:
        print("Failed to get transcription.")

if __name__ == "__main__":
    main()
