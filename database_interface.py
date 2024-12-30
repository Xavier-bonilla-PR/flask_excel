from openai import OpenAI
import os
from dotenv import load_dotenv

class DatabaseInterface:
    def __init__(self):
        # Initialize OpenAI client
        load_dotenv()
        self.client = OpenAI(api_key=os.getenv('AI_KEY'))
        self.conversation_history = [
            {"role": "system", "content": "You are a helpful assistant for a student attendance system."}
        ]
        self.max_history = 50  # Increased maximum number of messages to keep in history

    def send_message(self, message, message_type="text"):
        try:
            # Add user message to conversation history
            self.conversation_history.append({"role": "user", "content": message, "type": message_type})
            
            # Prepare the messages for the API call
            api_messages = [
                {"role": msg["role"], "content": msg["content"]}
                for msg in self.conversation_history
                if msg["role"] in ["system", "user", "assistant"]
            ]

            response = self.client.chat.completions.create(
                model="gpt-4",  # Using GPT-4 model
                messages=api_messages
            )

            assistant_response = response.choices[0].message.content

            # Add assistant's response to conversation history
            self.conversation_history.append({"role": "assistant", "content": assistant_response, "type": "text"})

            # Trim conversation history if it exceeds max_history
            if len(self.conversation_history) > self.max_history + 1:  # +1 for the system message
                self.conversation_history = self.conversation_history[:1] + self.conversation_history[-(self.max_history):]

            return assistant_response
        except Exception as e:
            print(f"Error in sending message to OpenAI: {e}")
            return "I'm sorry, I couldn't process your request at the moment."

    def add_image_analysis(self, image_description, analysis_result):
        # Add image analysis to conversation history
        self.conversation_history.append({"role": "user", "content": f"Analyzed image: {image_description}", "type": "image"})
        self.conversation_history.append({"role": "assistant", "content": f"Image analysis result: {analysis_result}", "type": "image_analysis"})

    def add_script_run(self, script_name, script_result):
        # Add script run to conversation history
        self.conversation_history.append({"role": "user", "content": f"Ran script: {script_name}", "type": "script"})
        self.conversation_history.append({"role": "assistant", "content": f"Script result: {script_result}", "type": "script_result"})

    def save_data(self):
        # Implement data saving logic
        print("Data saved successfully")

    def clear_history(self):
        # Clear conversation history except for the initial system message
        self.conversation_history = self.conversation_history[:1]
