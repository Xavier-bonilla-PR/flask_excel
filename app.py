from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, current_app, send_from_directory
from database_interface import DatabaseInterface
import subprocess
import os
import logging
from logging.handlers import RotatingFileHandler
import threading
from extract_data import AiderRunner
import time
import signal
import queue
import uuid
from werkzeug.utils import secure_filename
from image_llm import ImageLLM
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Set a secret key for flashing messages
db = DatabaseInterface()

# Configuration for file uploads
UPLOAD_FOLDER = 'temp_uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max-limit

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize the scheduler
scheduler = BackgroundScheduler()
scheduler.start()

def delete_file(filepath):
    try:
        os.remove(filepath)
        logger.info(f"Removed temporary file: {filepath}")
    except Exception as e:
        logger.error(f"Error deleting file {filepath}: {str(e)}")

def schedule_file_deletion(filepath):
    # Schedule file deletion after 1 hour
    scheduler.add_job(delete_file, 'date', run_date=datetime.now() + timedelta(hours=1), args=[filepath])
    logger.info(f"Scheduled deletion of {filepath} in 1 hour")

# Create a file handler
file_handler = RotatingFileHandler('app.log', maxBytes=10240, backupCount=10)
file_handler.setLevel(logging.INFO)

# Create a console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Create a formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Add the handlers to the logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Global flag to indicate if a script is running
script_running = threading.Event()

# Dictionary to store script processes and their input/output queues
script_processes = {}

def run_script_with_input(script_path):
    script_running.set()
    try:
        process = subprocess.Popen(['python', '-u', script_path], #added -u
                                   stdin=subprocess.PIPE, 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.PIPE, 
                                   text=True, 
                                   bufsize=1, 
                                   universal_newlines=True)
        
        input_queue = queue.Queue()
        output_queue = queue.Queue()
        
        def output_reader(stream, queue):
            
            for line in iter(stream.readline, ''): 
                queue.put(line)
            stream.close()
        
        threading.Thread(target=output_reader, args=(process.stdout, output_queue), daemon=True).start()
        threading.Thread(target=output_reader, args=(process.stderr, output_queue), daemon=True).start()
        
        return process, input_queue, output_queue
    finally:
        script_running.clear()

def get_scripts():
    excluded_scripts = ['app.py', 'database_interface.py', 'image_llm.py']
    return [f for f in os.listdir() if f.endswith('.py') and f not in excluded_scripts]

@app.route('/')
def index():
    scripts = get_scripts()
    return render_template('modern_chat.html', scripts=scripts)

@app.route('/send_message', methods=['POST'])
def send_message():
    message = request.json['message']
    logger.info(f"Received message: {message}")
    
    response = db.send_message(message)
    logger.info(f"Database response: {response}")
    
    scripts = get_scripts()
    return jsonify({'response': response, 'scripts': scripts})

def handleExtractDataScript():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400
    
    file_name = data.get('file_name')
    user_prompt = data.get('user_prompt')
    
    if not file_name or not user_prompt:
        return jsonify({'error': 'Missing file_name or user_prompt'}), 400
    
    runner = AiderRunner(file_name, user_prompt)
    result = runner.run()
    
    logger.info("extract_data.py execution successful")
    db.add_script_run('extract_data.py', result)
    return jsonify({'response': f"Script output:\n{result}"})

def handleAddDataScript():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400
    
    file_name = data.get('file_name')
    user_prompt = data.get('user_prompt')
    
    if not file_name or not user_prompt:
        return jsonify({'error': 'Missing file_name or user_prompt'}), 400
    
    runner = AiderRunner(file_name, user_prompt)
    result = runner.run()
    
    logger.info("add_data.py execution successful")
    db.add_script_run('add_data.py', result)
    return jsonify({'response': f"Script output:\n{result}"})

@app.route('/run_script/<script_name>', methods=['POST'])
def run_script(script_name):
    script_path = os.path.join(os.getcwd(), script_name)
    
    if not script_name.endswith('.py'):
        return jsonify({'error': 'Invalid script name. Must end with .py'}), 400
    
    if not os.path.isfile(script_path):
        logger.error(f"Script file not found: {script_path}")
        return jsonify({'error': f"Script file '{script_name}' not found"}), 404

    try:
        logger.info(f"Attempting to run script: {script_path}")
        
        if script_name == 'extract_data.py' or script_name == 'add_data.py':
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No JSON data provided'}), 400
            
            if script_name == 'extract_data.py':
                return handleExtractDataScript()
            else:
                return handleAddDataScript()
        else:
            process, input_queue, output_queue = run_script_with_input(script_path)
            script_processes[script_name] = (process, input_queue, output_queue)
            
            # Wait for initial output or a short timeout
            try:
                initial_output = []
                timeout = time.time() + 2  # 2 second timeout
                while time.time() < timeout:
                    try:
                        line = output_queue.get(block=False)
                        initial_output.append(line)
                        if '?' in line:  # Check if the line contains a question mark
                            return jsonify({
                                'input_required': True,
                                'prompt': ''.join(initial_output),
                                'response': ''.join(initial_output)
                            })
                    except queue.Empty:
                        if initial_output:
                            break
                        time.sleep(0.1)
                
                if initial_output:
                    result = ''.join(initial_output)
                    db.add_script_run(script_name, result)
                    return jsonify({'response': result})
                else:
                    # Check if the process has terminated
                    if process.poll() is not None:
                        result = 'Script completed with no output.'
                        db.add_script_run(script_name, result)
                        return jsonify({'response': result})
                    else:
                        return jsonify({
                            'input_required': True,
                            'prompt': 'Script is waiting for input:',
                            'response': 'Script is waiting for input:'
                        })
            
            except Exception as e:
                logger.error(f"Error reading script output: {str(e)}")
                return jsonify({'error': f"Error reading script output: {str(e)}"}), 500
    
    except Exception as e:
        logger.error(f"Unexpected error running script {script_name}: {str(e)}")
        return jsonify({'error': f"Unexpected error: {str(e)}"}), 500

@app.route('/script_input/<script_name>', methods=['POST'])
def script_input(script_name):
    if script_name not in script_processes:
        return jsonify({'error': 'No running script found with this name'}), 404
    
    process, input_queue, output_queue = script_processes[script_name]
    user_input = request.json.get('input')
    
    if not user_input:
        return jsonify({'error': 'No input provided'}), 400
    
    try:
        process.stdin.write(user_input + '\n')
        process.stdin.flush()
        
        # Wait for output or a short timeout
        try:
            output = []
            while True:
                try:
                    line = output_queue.get(timeout=0.5)
                    output.append(line)
                except queue.Empty:
                    break
            
            if not output:
                return jsonify({'input_required': True, 'prompt': 'Script is waiting for more input:'})
            else:
                return jsonify({'response': ''.join(output)})
        
        except Exception as e:
            logger.error(f"Error reading script output: {str(e)}")
            return jsonify({'error': f"Error reading script output: {str(e)}"}), 500
    
    except Exception as e:
        logger.error(f"Error sending input to script: {str(e)}")
        return jsonify({'error': f"Error sending input to script: {str(e)}"}), 500

@app.route('/analyze_image', methods=['POST'])
def analyze_image():
    if 'file' not in request.files:
        logger.error("No file part in the request")
        return jsonify({'error': 'No file part'})
    file = request.files['file']
    if file.filename == '':
        logger.error("No selected file")
        return jsonify({'error': 'No selected file'})
    if file and allowed_file(file.filename):
        filename = secure_filename(str(uuid.uuid4()) + os.path.splitext(file.filename)[1])
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            # Analyze the image
            image_llm = ImageLLM(filepath)
            results = image_llm.transcribe_image()
            
            # Create a URL for the image
            image_url = url_for('uploaded_file', filename=filename, _external=True)
            
            logger.info(f"Image analysis completed for {filename}")
            logger.info(f"Image URL: {image_url}")

            # Schedule file deletion after 1 hour
            schedule_file_deletion(filepath)

            # Add image analysis to conversation history
            db.add_image_analysis(filename, results)

            return jsonify({'results': results, 'image_url': image_url})
        except Exception as e:
            logger.error(f"Error analyzing image: {str(e)}")
            os.remove(filepath)  # Delete the file immediately if there's an error
            return jsonify({'error': f"Error analyzing image: {str(e)}"}), 500
    
    logger.error(f"Invalid file type: {file.filename}")
    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

def custom_reloader(app):
    stop_event = threading.Event()

    def signal_handler(signum, frame):
        print("\nReceived interrupt signal. Shutting down...")
        stop_event.set()
        os._exit(0)  # Force exit the program

    signal.signal(signal.SIGINT, signal_handler)

    def run_app():
        app.run(debug=True, use_reloader=False)

    def watch_files():
        previous = set(os.listdir())
        while not stop_event.is_set():
            time.sleep(1)
            current = set(os.listdir())
            new_files = current - previous
            if new_files:
                # Check if the new files are Python files created by add_data.py
                if any(file.endswith('.py') for file in new_files):
                    logger.info(f"New Python file(s) created: {new_files}")
                else:
                    while script_running.is_set():
                        time.sleep(0.1)
                    os._exit(3)
            previous = current

    app_thread = threading.Thread(target=run_app, daemon=True)
    watch_thread = threading.Thread(target=watch_files, daemon=True)

    app_thread.start()
    watch_thread.start()

    try:
        while not stop_event.is_set():
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received. Shutting down...")
    finally:
        stop_event.set()
        os._exit(0)  # Force exit the program

if __name__ == '__main__':
    custom_reloader(app)
