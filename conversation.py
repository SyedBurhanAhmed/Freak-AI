from flask import Flask, request, jsonify, session, send_file, render_template, redirect, url_for
import os
import io
import wave
import base64
import json
import speech_recognition as sr
from gtts import gTTS
from pydub import AudioSegment
from threading import Thread
import secrets
import time
from datetime import datetime
from app import *
import serial
import json
import threading
import time
from datetime import datetime
import queue
import logging


class ESP32DHT11SensoryMemoryManager:
    def __init__(self, esp32_ip="192.168.43.23"):  # Your ESP32 IP from logs
        self.esp32_ip = esp32_ip
        self.sensor_endpoint = f"http://{esp32_ip}/sensor"
        self.esp32_status_endpoint = f"http://{esp32_ip}/"

        self.sensor_data = {
            'temperature': None,
            'humidity': None,
            'timestamp': None,
            'sensor_type': 'DHT11',
            'memory_type': 'SensoryMemory',
            'status': 'disconnected',
            'comfort_score': 0,
            'recommendations': []
        }

        self.data_queue = queue.Queue(maxsize=100)
        self.running = False
        self.lock = threading.Lock()
        self.current_user_email = None

        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        # Test connection and start monitoring
        self.connect()

    def connect(self):
        """Test ESP32 connection and start monitoring"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.get(self.esp32_status_endpoint, timeout=5)
                if response.status_code == 200:
                    self.running = True
                    self.sensor_data['status'] = 'connected'
                    self.logger.info(f"Connected to ESP32 DHT11 on {self.esp32_ip}")

                    # Start monitoring thread
                    self.start_monitoring()
                    return True

            except Exception as e:
                self.logger.error(f"ESP32 connection attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    self.sensor_data['status'] = 'error'
                    self.logger.warning("ESP32 DHT11 sensor unavailable - continuing without sensor")
                    return False
                time.sleep(2)

    def start_monitoring(self):
        """Start background monitoring thread"""
        self.reader_thread = threading.Thread(target=self.read_sensor_data, daemon=True)
        self.processor_thread = threading.Thread(target=self.process_sensor_data, daemon=True)

        self.reader_thread.start()
        self.processor_thread.start()

    def read_sensor_data(self):
        """Continuous reading thread for ESP32 sensor data"""
        while self.running:
            try:
                response = requests.get(self.sensor_endpoint, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    self.data_queue.put(data, timeout=1)
                else:
                    self.logger.warning(f"ESP32 sensor request failed: {response.status_code}")

            except requests.RequestException as e:
                self.logger.error(f"ESP32 sensor read error: {e}")
                with self.lock:
                    self.sensor_data['status'] = 'disconnected'

            except Exception as e:
                self.logger.error(f"Unexpected sensor read error: {e}")

            time.sleep(30)  # Read every 30 seconds

    def process_sensor_data(self):
        """Process queued sensor data from ESP32"""
        while self.running:
            try:
                data = self.data_queue.get(timeout=1)

                with self.lock:
                    if self.validate_sensor_data(data):
                        # Update sensor data with ESP32 information
                        self.sensor_data.update({
                            'temperature': data.get('temperature'),
                            'humidity': data.get('humidity'),
                            'timestamp': data.get('timestamp'),
                            'sensor_type': 'DHT11',
                            'memory_type': 'SensoryMemory',
                            'status': data.get('status', 'valid'),
                            'comfort_score': data.get('comfort_score', 0),
                            'recommendations': data.get('recommendations', '').split('; ') if data.get(
                                'recommendations') else [],
                            'python_timestamp': datetime.now().isoformat(),
                            'esp32_ip': data.get('esp32_ip')
                        })

                        # Save to Neo4j
                        threading.Thread(
                            target=self.save_esp32_sensory_memory,
                            args=(data.copy(),),
                            daemon=True
                        ).start()

                        self.logger.info(f"ESP32 DHT11 updated: {data.get('temperature')}°C, {data.get('humidity')}%")

                self.data_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"ESP32 data processing error: {e}")

    def validate_sensor_data(self, data):
        """Validate ESP32 DHT11 sensor data"""
        if not isinstance(data, dict):
            return False

        # Check if data has required fields
        if 'temperature' not in data or 'humidity' not in data:
            return False

        temp = data.get('temperature')
        humidity = data.get('humidity')

        # Validate data ranges
        if temp is not None and (temp < -40 or temp > 80):  # Extended range for ESP32
            self.logger.warning(f"Temperature out of range: {temp}")
            return False

        if humidity is not None and (humidity < 0 or humidity > 100):
            self.logger.warning(f"Humidity out of range: {humidity}")
            return False

        return True

    def save_esp32_sensory_memory(self, sensor_data):
        """Save ESP32 DHT11 data to Neo4j as DHT11:SensoryMemory"""
        try:
            driver = connect_neo4j()
            if not driver:
                self.logger.warning("Neo4j not available, skipping ESP32 sensor data save")
                return

            neo4j_session = driver.session()
            timestamp = datetime.now().isoformat()

            # Create DHT11:SensoryMemory node with ESP32 data
            neo4j_session.run("""
                CREATE (s:DHT11:SensoryMemory {
                    temperature: $temperature,
                    humidity: $humidity,
                    timestamp: $timestamp,
                    sensor_type: $sensor_type,
                    memory_type: $memory_type,
                    status: $status,
                    data_quality: $quality,
                    comfort_score: $comfort_score,
                    recommendations: $recommendations,
                    data_source: $data_source,
                    esp32_ip: $esp32_ip,
                    unit_temperature: 'Celsius',
                    unit_humidity: 'Percent'
                })
            """,
                              temperature=sensor_data.get('temperature'),
                              humidity=sensor_data.get('humidity'),
                              timestamp=timestamp,
                              sensor_type='DHT11',
                              memory_type='SensoryMemory',
                              status=sensor_data.get('status', 'valid'),
                              quality='esp32_validated',
                              comfort_score=sensor_data.get('comfort_score', 0),
                              recommendations=sensor_data.get('recommendations', ''),
                              data_source='ESP32',
                              esp32_ip=sensor_data.get('esp32_ip', self.esp32_ip)
                              )

            # Link to current user if available
            if hasattr(self, 'current_user_email') and self.current_user_email:
                neo4j_session.run("""
                    MATCH (u:User {email: $email}), (s:DHT11:SensoryMemory {timestamp: $timestamp})
                    MERGE (u)-[:HAS_SENSOR_READING]->(s)
                """, email=self.current_user_email, timestamp=timestamp)

            neo4j_session.close()
            driver.close()

            self.logger.info(f"Saved ESP32 DHT11:SensoryMemory - Temp: {sensor_data.get('temperature')}°C")

        except Exception as e:
            self.logger.error(f"Neo4j ESP32 save error: {e}")

    def set_current_user(self, email):
        """Set current user for sensor data linking"""
        self.current_user_email = email
        self.logger.info(f"ESP32 DHT11 sensor linked to user: {email}")

    def get_latest_readings(self):
        """Thread-safe data access"""
        with self.lock:
            return self.sensor_data.copy()

    def get_environmental_context(self):
        """Get comprehensive environmental context from ESP32"""
        with self.lock:
            data = self.sensor_data.copy()

            if data['status'] not in ['valid', 'connected']:
                return None

            temp = data.get('temperature')
            humidity = data.get('humidity')

            if temp is None or humidity is None:
                return None

            return {
                'temperature': temp,
                'humidity': humidity,
                'comfort_level': data.get('comfort_score', 0),
                'recommendations': data.get('recommendations', []),
                'timestamp': data.get('timestamp'),
                'sensor_type': 'DHT11',
                'memory_type': 'SensoryMemory',
                'data_source': 'ESP32',
                'esp32_ip': data.get('esp32_ip')
            }

    def calculate_comfort_score(self, temp, humidity):
        """Calculate comfort score (handled by ESP32, but kept for compatibility)"""
        temp_score = max(0, min(100, 100 - abs(temp - 23) * 10))
        humidity_score = max(0, min(100, 100 - abs(humidity - 50) * 2))
        return (temp_score + humidity_score) / 2

    def get_recommendations(self, temp, humidity):
        """Get environmental recommendations (handled by ESP32, but kept for compatibility)"""
        recommendations = []

        if temp > 26:
            recommendations.append("Room temperature is high - consider cooling")
        elif temp < 20:
            recommendations.append("Room temperature is low - consider warming")

        if humidity > 60:
            recommendations.append("Humidity is high - consider dehumidifying")
        elif humidity < 40:
            recommendations.append("Humidity is low - consider humidifying")

        if not recommendations:
            recommendations.append("Environmental conditions are optimal")

        return recommendations

    def disconnect(self):
        """Clean shutdown"""
        self.running = False
        self.logger.info("ESP32 DHT11 sensor manager disconnected")

    def get_esp32_status(self):
        """Get ESP32 device status"""
        try:
            response = requests.get(self.esp32_status_endpoint, timeout=3)
            if response.status_code == 200:
                return {
                    'status': 'connected',
                    'ip': self.esp32_ip,
                    'response_time': response.elapsed.total_seconds()
                }
        except Exception as e:
            return {
                'status': 'disconnected',
                'error': str(e),
                'ip': self.esp32_ip
            }


# Initialize global ESP32 sensor manager
dht11_sensor = ESP32DHT11SensoryMemoryManager()


# Updated functions to work with ESP32 system
def get_dht11_temperature():
    """Get current temperature from ESP32 DHT11 sensor"""
    temp = dht11_sensor.get_latest_readings().get('temperature')
    if temp is not None:
        myBot.setPredicate("dht11_temperature", str(temp))
        myBot.setPredicate("dht11_temp_unit", "°C")
        myBot.setPredicate("sensor_type", "DHT11")
        myBot.setPredicate("data_source", "ESP32")
    else:
        myBot.setPredicate("dht11_temperature", "unavailable")
    return temp


def get_dht11_humidity():
    """Get current humidity from ESP32 DHT11 sensor"""
    humidity = dht11_sensor.get_latest_readings().get('humidity')
    if humidity is not None:
        myBot.setPredicate("dht11_humidity", str(humidity))
        myBot.setPredicate("dht11_humidity_unit", "%")
        myBot.setPredicate("sensor_type", "DHT11")
        myBot.setPredicate("data_source", "ESP32")
    else:
        myBot.setPredicate("dht11_humidity", "unavailable")
    return humidity


def get_dht11_status():
    """Get ESP32 DHT11 sensor status"""
    data = dht11_sensor.get_latest_readings()
    status = data.get('status', 'unknown')
    myBot.setPredicate("dht11_status", status)
    myBot.setPredicate("sensor_type", "DHT11")
    myBot.setPredicate("data_source", "ESP32")
    return status


def analyze_dht11_environment():
    """Analyze environment using ESP32 DHT11 readings"""
    context = dht11_sensor.get_environmental_context()

    if context:
        myBot.setPredicate("dht11_comfort_score", str(int(context['comfort_level'])))
        myBot.setPredicate("dht11_recommendations", "; ".join(context['recommendations']))
        myBot.setPredicate("environmental_status", "analyzed")
        myBot.setPredicate("data_source", "ESP32")
    else:
        myBot.setPredicate("environmental_status", "unavailable")

    return context


def get_dht11_memory_data():
    """Get recent ESP32 DHT11 sensory memory data from Neo4j"""
    try:
        driver = connect_neo4j()
        if not driver:
            return []

        neo4j_session = driver.session()

        # Get recent DHT11 readings from ESP32
        query = """
        MATCH (s:DHT11:SensoryMemory)
        WHERE s.data_source = 'ESP32'
        RETURN s.temperature as temp, s.humidity as humidity, s.timestamp as timestamp, 
               s.comfort_score as comfort_score, s.recommendations as recommendations
        ORDER BY s.timestamp DESC
        LIMIT 10
        """

        result = neo4j_session.run(query)
        readings = []

        for record in result:
            readings.append({
                'temperature': record['temp'],
                'humidity': record['humidity'],
                'timestamp': record['timestamp'],
                'comfort_score': record['comfort_score'],
                'recommendations': record['recommendations'],
                'data_source': 'ESP32'
            })

        neo4j_session.close()
        driver.close()

        return readings

    except Exception as e:
        print(f"Error retrieving ESP32 DHT11 memory data: {e}")
        return []


def get_esp32_device_status():
    """Get ESP32 device status"""
    return dht11_sensor.get_esp32_status()


def set_esp32_sensor_user(email):
    """Set current user for ESP32 sensor data"""
    dht11_sensor.set_current_user(email)


# Compatibility function for existing code
def get_environmental_context():
    """Get environmental context (compatibility function)"""
    return dht11_sensor.get_environmental_context()


app = Flask(__name__)
app.secret_key = 'your-secret-key'

# Configuration
UPLOAD_FOLDER = 'audio_uploads'
TTS_FILENAME = "tts_latest.mp3"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Store active sessions globally
active_sessions = {}


# =====================================
# STANDALONE BOT RESPONSE FUNCTION
# =====================================

def get_bot_response(query, user_email=None, user_fact_file=None, username=None):
    """
    Standalone function to get bot response
    """
    if not query or query.strip() == "":
        return {
            "response": "Please provide a message.",
            "status": "error",
            "error": "Empty query"
        }

    try:
        # Use provided user data or create default
        if user_email and user_fact_file:
            email = user_email
            fact_file = user_fact_file
            user_name = username or "User"
        else:
            # Use session data if available, otherwise create default
            email = session.get("email", "default@voice.local")
            fact_file = session.get("fact_file", "prolog/facts/default.pl")
            user_name = session.get("username", "User")

        print(f"DEBUG: Processing query for user: {user_name} ({email})")

        # Create default fact file if it doesn't exist
        if not os.path.exists(fact_file):
            os.makedirs(os.path.dirname(fact_file), exist_ok=True)
            with open(fact_file, 'w') as f:
                f.write("% Default facts\n")
                f.write("fact(user, voice_enabled, true).\n")

        # Load knowledge base
        kb.from_file(fact_file)

        # Set bot predicate
        myBot.setPredicate("username", user_name)

        # Process the query
        myBot.respond(query)
        prompt_check()
        response = myBot.respond(query)

        # ENHANCED interaction logging
        print(f"DEBUG: Checking interaction logging for email: {email}")

        # Log interaction for ALL users (not just non-default)
        if email and email.strip() != "":
            try:
                print(f"DEBUG: Starting interaction logging for {email}")

                mock_session = {
                    'email': email,
                    'username': user_name,
                    'fact_file': fact_file
                }

                print(f"DEBUG: Mock session created: {mock_session}")

                # # Try synchronous call first for debugging
                # print(f"DEBUG: Calling async_create_interaction synchronously...")
                # async_create_interaction(email, query, response, mock_session)
                # print(f"DEBUG: Synchronous call completed successfully")

                # Then do async call
                print(f"DEBUG: Starting async thread...")
                thread = Thread(target=async_create_interaction, args=(email, query, response, mock_session))
                thread.daemon = True
                thread.start()
                print(f"DEBUG: Async thread started")

            except Exception as e:
                print(f"ERROR: Interaction logging failed: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"DEBUG: Skipping interaction logging - no valid email")

        set_sentiment()

        # Clear predicates
        for key in [
            "mood", "word", "dob_person", "age_person", "gender_person",
            "rel", "person1", "gender", "dob", "relation", "person",
            "other_dob_person", "other_dob", "other_gender_person", "other_gender",
            "other_person1", "other_person2", "other_relation", "delete", "user_input_name",
            "get_dht11_temperature", "get_dht11_humidity", "get_dht11_status",
            "analyze_dht11_environment", "get_dht11_memory"
        ]:
            myBot.setPredicate(key, "")

        return {
            "response": response,
            "status": "success",
            "user": user_name,
            "recognized_text": query
        }

    except Exception as e:
        print(f"Error in get_bot_response: {e}")
        import traceback
        traceback.print_exc()
        return {
            "response": "Sorry, I encountered an error processing your message.",
            "status": "error",
            "error": str(e)
        }


def get_bot_response_with_sensor(query, user_email, user_fact_file, username, sensor_data):
    """Enhanced bot response with sensor data integration"""
    if not query or query.strip() == "":
        return {
            "response": "Please provide a message.",
            "status": "error",
            "error": "Empty query"
        }

    try:
        # Create default fact file if it doesn't exist
        if not os.path.exists(user_fact_file):
            os.makedirs(os.path.dirname(user_fact_file), exist_ok=True)
            with open(user_fact_file, 'w') as f:
                f.write("% Default facts\n")
                f.write("fact(user, voice_enabled, true).\n")

        # Load knowledge base
        kb.from_file(user_fact_file)

        # Set bot predicate
        myBot.setPredicate("username", username)

        # Set sensor data predicates if available
        if sensor_data and sensor_data.get('status') == 'valid':
            myBot.setPredicate("dht11_temperature", str(sensor_data.get('temperature', 'unavailable')))
            myBot.setPredicate("dht11_humidity", str(sensor_data.get('humidity', 'unavailable')))
            myBot.setPredicate("dht11_comfort_score", str(int(sensor_data.get('comfort_score', 0))))
            myBot.setPredicate("dht11_recommendations", sensor_data.get('recommendations', 'No recommendations'))
            myBot.setPredicate("dht11_status", "valid")
            myBot.setPredicate("sensor_type", "DHT11")
            myBot.setPredicate("dht11_temp_unit", "°C")
            myBot.setPredicate("dht11_humidity_unit", "%")
        else:
            myBot.setPredicate("dht11_temperature", "unavailable")
            myBot.setPredicate("dht11_humidity", "unavailable")
            myBot.setPredicate("dht11_status", "error")

        # Process the query
        myBot.respond(query)
        prompt_check()
        response = myBot.respond(query)

        # Log interaction
        try:
            mock_session = {
                'email': user_email,
                'username': username,
                'fact_file': user_fact_file
            }
            Thread(target=async_create_interaction, args=(user_email, query, response, mock_session)).start()
        except Exception as e:
            print(f"Interaction logging error: {e}")

        # Save sensor data to Neo4j if available
        if sensor_data and sensor_data.get('status') == 'valid':
            try:
                Thread(target=save_esp32_sensor_data, args=(sensor_data, user_email)).start()
            except Exception as e:
                print(f"Sensor data save error: {e}")

        set_sentiment()

        # Clear predicates
        for key in [
            "mood", "word", "dob_person", "age_person", "gender_person",
            "rel", "person1", "gender", "dob", "relation", "person",
            "other_dob_person", "other_dob", "other_gender_person", "other_gender",
            "other_person1", "other_person2", "other_relation", "delete", "user_input_name",
            "dht11_temperature", "dht11_humidity", "dht11_status",
            "dht11_comfort_score", "dht11_recommendations", "sensor_type",
            "dht11_temp_unit", "dht11_humidity_unit"
        ]:
            myBot.setPredicate(key, "")

        return {
            "response": response,
            "status": "success",
            "user": username,
            "recognized_text": query
        }

    except Exception as e:
        print(f"Error in get_bot_response_with_sensor: {e}")
        return {
            "response": "Sorry, I encountered an error processing your message.",
            "status": "error",
            "error": str(e)
        }


def save_esp32_sensor_data(sensor_data, user_email):
    """Save ESP32 sensor data to Neo4j"""
    try:
        driver = connect_neo4j()
        if not driver:
            return

        neo4j_session = driver.session()
        timestamp = datetime.now().isoformat()

        # Create sensor reading node
        neo4j_session.run("""
            CREATE (s:DHT11:SensoryMemory {
                temperature: $temperature,
                humidity: $humidity,
                timestamp: $timestamp,
                sensor_type: $sensor_type,
                memory_type: $memory_type,
                status: $status,
                comfort_score: $comfort_score,
                recommendations: $recommendations,
                data_source: $data_source
            })
        """,
                          temperature=sensor_data.get('temperature'),
                          humidity=sensor_data.get('humidity'),
                          timestamp=timestamp,
                          sensor_type='DHT11',
                          memory_type='SensoryMemory',
                          status=sensor_data.get('status'),
                          comfort_score=sensor_data.get('comfort_score'),
                          recommendations=sensor_data.get('recommendations'),
                          data_source='ESP32'
                          )

        # Link to user
        neo4j_session.run("""
            MERGE (u:User {email: $email})
            WITH u
            MATCH (s:DHT11:SensoryMemory {timestamp: $timestamp})
            MERGE (u)-[:HAS_SENSOR_READING]->(s)
        """, email=user_email, timestamp=timestamp)

        neo4j_session.close()
        driver.close()

        print(f"Saved ESP32 sensor data - Temp: {sensor_data.get('temperature')}°C")

    except Exception as e:
        print(f"Neo4j save error: {e}")


# =====================================
# WEB AUTHENTICATION ROUTES
# =====================================

@app.route("/")
def home():
    if 'email' in session and 'username' in session:
        return render_template("home.html", username=session['username'])
    else:
        return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get("email")
        password = request.form.get("password")

        if validate_data(email, password):
            session["email"] = email
            session["username"] = get_username(email)
            create_episode(email, session)
            fact_path = f"prolog/facts/{email.replace('@', '_at_')}.pl"
            session["fact_file"] = fact_path
            myBot.setPredicate("username", session["username"])
            return redirect(url_for('home') + '?success=login')
        else:
            return redirect(url_for('login') + '?error=invalid')

    return render_template('login.html')


@app.route('/logout')
def logout():
    if "email" in session:
        end_episode(session["email"], session)
    session.clear()
    return redirect(url_for('login'))


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if password != confirm_password:
            return redirect(url_for('signup') + '?error=password_mismatch')

        if check_email(email):
            return redirect(url_for('signup') + '?error=email_exists')
        if not validate_email(email):
            return redirect(url_for('signup') + '?error=invalid_email')
        store_credentials(name, email, password)
        return redirect(url_for('login') + '?success=signup')

    return render_template('signup.html')


# =====================================
# ESP32 AUTHENTICATION ROUTES
# =====================================

@app.route('/esp32_login', methods=['POST'])
def esp32_login():
    """ESP32 direct login endpoint"""
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return jsonify({"success": False, "error": "Email and password required"}), 400

        if validate_data(email, password):
            username = get_username(email)
            fact_path = f"prolog/facts/{email.replace('@', '_at_')}.pl"

            # Create episode for ESP32
            try:
                mock_session = {
                    'email': email,
                    'username': username,
                    'fact_file': fact_path
                }
                create_episode(email, mock_session)
            except Exception as e:
                print(f"Episode creation error: {e}")

            return jsonify({
                "success": True,
                "email": email,
                "username": username,
                "fact_file": fact_path,
                "message": "Login successful"
            }), 200
        else:
            return jsonify({"success": False, "error": "Invalid credentials"}), 401

    except Exception as e:
        print(f"ESP32 login error: {e}")
        return jsonify({"success": False, "error": "Server error"}), 500


@app.route('/esp32_signup', methods=['POST'])
def esp32_signup():
    """ESP32 direct signup endpoint"""
    try:
        data = request.get_json()
        name = data.get('name')
        email = data.get('email')
        password = data.get('password')
        confirm_password = data.get('confirm_password')

        if not all([name, email, password, confirm_password]):
            return jsonify({"success": False, "error": "All fields required"}), 400

        if password != confirm_password:
            return jsonify({"success": False, "error": "Passwords don't match"}), 400

        if check_email(email):
            return jsonify({"success": False, "error": "Email already exists"}), 400

        if not validate_email(email):
            return jsonify({"success": False, "error": "Invalid email format"}), 400

        if store_credentials(name, email, password):
            return jsonify({
                "success": True,
                "email": email,
                "name": name,
                "message": "Account created successfully"
            }), 200
        else:
            return jsonify({"success": False, "error": "Failed to create account"}), 500

    except Exception as e:
        print(f"ESP32 signup error: {e}")
        return jsonify({"success": False, "error": "Server error"}), 500


# =====================================
# AUDIO PROCESSING ROUTES
# =====================================

@app.route('/process_audio_chat', methods=['POST'])
def process_audio_chat():
    """Basic audio processing without TTS"""
    audio_data = request.get_data()
    if not audio_data:
        return jsonify({"error": "No audio data received"}), 400

    print(f"Received audio data: {len(audio_data)} bytes")

    # Convert raw audio to WAV format
    wav_io = io.BytesIO()
    try:
        with wave.open(wav_io, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(1)
            wf.setframerate(8000)
            wf.writeframes(audio_data)
    except Exception as e:
        return jsonify({"error": f"Failed to create WAV: {str(e)}"}), 500

    wav_io.seek(0)

    # Speech recognition
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(wav_io) as source:
            recognizer.adjust_for_ambient_noise(source)
            audio_record = recognizer.record(source)
        recognized_text = recognizer.recognize_google(audio_record)
        print(f"Recognized text: {recognized_text}")
    except sr.UnknownValueError:
        recognized_text = "Could not understand audio"
    except Exception as e:
        recognized_text = f"Recognition error: {e}"

    # Use standalone function for bot response
    bot_result = get_bot_response(recognized_text)

    # Save audio file for debugging
    audio_filename = f"audio_{len(audio_data)}_bytes.raw"
    audio_path = os.path.join(UPLOAD_FOLDER, audio_filename)
    with open(audio_path, 'wb') as f:
        f.write(audio_data)

    return jsonify({
        "recognized_text": recognized_text,
        "chatbot_response": bot_result["response"],
        "audio_saved": audio_filename,
        "status": "success"
    }), 200


@app.route('/process_audio_chat_tts', methods=['POST'])
def process_audio_chat_tts():
    """Process audio with TTS support for ESP32 direct authentication"""
    # Check for ESP32 headers
    user_email = request.headers.get('User-Email')
    user_fact_file = request.headers.get('User-Fact-File')
    user_name = request.headers.get('User-Name')

    if user_email and user_fact_file and user_name:
        # ESP32 direct authentication
        print(f"ESP32 request from {user_name} ({user_email})")
    elif "email" in session:
        # Regular web session
        user_email = session["email"]
        user_fact_file = session["fact_file"]
        user_name = session["username"]
    else:
        return jsonify({"error": "Authentication required"}), 401

    audio_data = request.get_data()
    if not audio_data:
        return jsonify({"error": "No audio data received"}), 400

    # Convert raw audio to WAV format
    wav_io = io.BytesIO()
    try:
        with wave.open(wav_io, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(1)
            wf.setframerate(8000)
            wf.writeframes(audio_data)
    except Exception as e:
        return jsonify({"error": f"Failed to create WAV: {str(e)}"}), 500

    wav_io.seek(0)

    # Speech recognition
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(wav_io) as source:
            recognizer.adjust_for_ambient_noise(source)
            audio_record = recognizer.record(source)
        recognized_text = recognizer.recognize_google(audio_record)
        print(f"Recognized text: {recognized_text}")
    except sr.UnknownValueError:
        recognized_text = "Could not understand audio"
    except Exception as e:
        recognized_text = f"Recognition error: {e}"

    # Use the standalone function for bot response
    bot_result = get_bot_response(recognized_text, user_email, user_fact_file, user_name)

    if bot_result["status"] != "success":
        return jsonify({"error": bot_result["response"]}), 500

    # Generate TTS audio
    try:
        tts = gTTS(text=bot_result["response"], lang='en', slow=False)
        tts_io = io.BytesIO()
        tts.write_to_fp(tts_io)
        tts_io.seek(0)
        tts_audio_bytes = tts_io.read()

        tts_file_path = os.path.join(UPLOAD_FOLDER, TTS_FILENAME)
        with open(tts_file_path, "wb") as f:
            f.write(tts_audio_bytes)

        print(f"TTS audio saved: {len(tts_audio_bytes)} bytes")

    except Exception as e:
        return jsonify({"error": f"TTS conversion failed: {str(e)}"}), 500

    return jsonify({
        "recognized_text": recognized_text,
        "chatbot_response": bot_result["response"],
        "user": bot_result["user"],
        "tts_filename": TTS_FILENAME,
        "status": "success"
    }), 200


@app.route('/esp32_audio_with_sensor', methods=['POST'])
def esp32_audio_with_sensor():
    """Process ESP32 audio with integrated sensor data"""
    # Get user authentication from headers
    user_email = request.headers.get('User-Email')
    user_fact_file = request.headers.get('User-Fact-File')
    user_name = request.headers.get('User-Name')
    sensor_data_json = request.headers.get('Sensor-Data')

    if not all([user_email, user_fact_file, user_name]):
        return jsonify({"error": "Authentication required"}), 401

    # Parse sensor data
    sensor_data = None
    if sensor_data_json:
        try:
            sensor_data = json.loads(sensor_data_json)
        except json.JSONDecodeError:
            print("Warning: Invalid sensor data JSON")

    audio_data = request.get_data()
    if not audio_data:
        return jsonify({"error": "No audio data received"}), 400

    print(f"ESP32 request from {user_name} with sensor data")

    # Convert raw audio to WAV format
    wav_io = io.BytesIO()
    try:
        with wave.open(wav_io, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(1)
            wf.setframerate(8000)
            wf.writeframes(audio_data)
    except Exception as e:
        return jsonify({"error": f"Failed to create WAV: {str(e)}"}), 500

    wav_io.seek(0)

    # Speech recognition
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(wav_io) as source:
            recognizer.adjust_for_ambient_noise(source)
            audio_record = recognizer.record(source)
        recognized_text = recognizer.recognize_google(audio_record)
        print(f"Recognized text: {recognized_text}")
    except sr.UnknownValueError:
        recognized_text = "Could not understand audio"
    except Exception as e:
        recognized_text = f"Recognition error: {e}"

    # Enhanced bot response with sensor integration
    bot_result = get_bot_response_with_sensor(recognized_text, user_email, user_fact_file, user_name, sensor_data)

    if bot_result["status"] != "success":
        return jsonify({"error": bot_result["response"]}), 500

    # Generate TTS audio
    try:
        tts = gTTS(text=bot_result["response"], lang='en', slow=False)
        tts_io = io.BytesIO()
        tts.write_to_fp(tts_io)
        tts_io.seek(0)
        tts_audio_bytes = tts_io.read()

        tts_file_path = os.path.join(UPLOAD_FOLDER, TTS_FILENAME)
        with open(tts_file_path, "wb") as f:
            f.write(tts_audio_bytes)

        print(f"TTS audio saved: {len(tts_audio_bytes)} bytes")

    except Exception as e:
        return jsonify({"error": f"TTS conversion failed: {str(e)}"}), 500

    return jsonify({
        "recognized_text": recognized_text,
        "chatbot_response": bot_result["response"],
        "user": bot_result["user"],
        "sensor_data": sensor_data,
        "tts_filename": TTS_FILENAME,
        "status": "success"
    }), 200


@app.route('/download_tts', methods=['GET'])
def download_tts():
    """Download TTS audio for ESP32"""
    tts_file_path = os.path.join(UPLOAD_FOLDER, TTS_FILENAME)

    if not os.path.exists(tts_file_path):
        print(f"TTS file not found: {tts_file_path}")
        return jsonify({"error": "TTS file not found"}), 404

    try:
        print(f"Converting TTS file: {tts_file_path}")
        sound = AudioSegment.from_mp3(tts_file_path)
        sound = sound.set_frame_rate(8000).set_channels(1).set_sample_width(1)

        wav_io = io.BytesIO()
        sound.export(wav_io, format="wav")
        wav_io.seek(0)

        print(f"TTS file converted successfully, size: {len(wav_io.getvalue())} bytes")

        return send_file(
            wav_io,
            mimetype="audio/wav",
            as_attachment=True,
            download_name="tts_latest.wav"
        )

    except Exception as e:
        print(f"TTS conversion error: {e}")
        return jsonify({"error": f"Conversion error: {str(e)}"}), 500


# =====================================
# LEGACY ROUTES (for backward compatibility)
# =====================================

@app.route('/get_session_info', methods=['GET'])
def get_session_info():
    """Get current session information"""
    if 'email' not in session:
        return jsonify({"error": "Not logged in"}), 401

    return jsonify({
        "session_id": session.get('_id', 'unknown'),
        "fact_file": session.get('fact_file'),
        "email": session.get('email'),
        "username": session.get('username'),
        "session_data": dict(session)
    })


@app.route('/register_session', methods=['POST'])
def register_session():
    """Register current session for ESP32 access"""
    if 'email' not in session:
        return jsonify({"error": "Not logged in"}), 401

    session_token = secrets.token_urlsafe(16)
    active_sessions[session_token] = {
        'fact_file': session['fact_file'],
        'email': session['email'],
        'username': session['username'],
        'created_at': time.time()
    }

    return jsonify({
        "session_token": session_token,
        "fact_file": session['fact_file'],
        "email": session['email']
    })


def generate_chatbot_response(query):
    """Legacy function for backward compatibility"""
    result = get_bot_response(query)
    return result.get("response", "Error processing request")


# =====================================
# ANALYTICS ROUTES
# =====================================

@app.route('/analytics')
def analytics():
    if 'email' not in session:
        return jsonify({"error": "Please log in to view analytics."}), 401

    try:
        driver = connect_neo4j()
        neo4j_session = driver.session()

        analytics_data = {
            "user_stats": get_user_statistics(session['email'], neo4j_session),
            "graph_stats": get_complete_graph_statistics(neo4j_session),
            "memory_stats": get_memory_statistics(session['email'], neo4j_session),
            "interaction_stats": get_interaction_statistics(session['email'], neo4j_session)
        }

        return jsonify(analytics_data), 200

    except Exception as e:
        print(f"Analytics error: {e}")
        return jsonify({"error": "Failed to fetch analytics data"}), 500
    finally:
        try:
            neo4j_session.close()
            driver.close()
        except:
            pass


@app.route('/api/graph_data')
def get_complete_graph_data():
    if 'email' not in session:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        driver = connect_neo4j()
        neo4j_session = driver.session()
    except Exception as e:
        return jsonify({"error": "Database connection failed"}), 503

    try:
        # Get ALL nodes
        nodes_query = """
        MATCH (n)
        RETURN elementId(n) as id, labels(n) as labels, properties(n) as properties
        """
        nodes_result = neo4j_session.run(nodes_query)

        # Get ALL relationships
        edges_query = """
        MATCH (n1)-[r]->(n2)
        RETURN elementId(n1) as source, elementId(n2) as target, type(r) as type, properties(r) as properties
        """
        edges_result = neo4j_session.run(edges_query)

        # Format nodes for visualization
        nodes = []
        for record in nodes_result:
            node_id = record['id']
            labels = record['labels']
            properties = record['properties']

            # Create display label
            display_label = ""
            if 'name' in properties:
                display_label = properties['name']
            elif 'email' in properties:
                display_label = properties['email']
            elif 'sentence_text' in properties:
                display_label = properties['sentence_text'][:50] + "..." if len(properties['sentence_text']) > 50 else \
                properties['sentence_text']
            elif 'full_text' in properties:
                display_label = properties['full_text'][:30] + "..." if len(properties['full_text']) > 30 else \
                properties['full_text']
            elif 'word_text' in properties:
                display_label = properties['word_text']
            elif 'session_id' in properties:
                display_label = f"Episode {properties['session_id'][:8]}"
            elif 'interaction_id' in properties:
                display_label = f"Interaction {properties['interaction_id'][:8]}"
            else:
                display_label = f"{labels[0] if labels else 'Node'}"

            # Color coding
            color = "#97c2fc"  # default
            if "User" in labels:
                color = "#ff6b6b"
            elif "Person" in labels:
                color = "#4ecdc4"
            elif "Text" in labels or "SensoryMemory" in labels:
                color = "#ffe66d"
            elif "Sentence" in labels:
                color = "#a8e6cf"
            elif "Word" in labels:
                color = "#dcedc1"
            elif "Interaction" in labels:
                color = "#ffb3ba"
            elif "Episode" in labels:
                color = "#bae1ff"
            elif "Agent" in labels:
                color = "#ffd93d"

            nodes.append({
                "id": node_id,
                "label": display_label,
                "color": color,
                "title": f"Labels: {', '.join(labels)}\nProperties: {str(properties)}",
                "group": labels[0] if labels else "Unknown"
            })

        # Format edges
        edges = []
        for record in edges_result:
            edges.append({
                "from": record['source'],
                "to": record['target'],
                "label": record['type'],
                "title": f"Type: {record['type']}\nProperties: {str(record['properties'])}"
            })

        return jsonify({
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "total_nodes": len(nodes),
                "total_edges": len(edges)
            }
        })

    except Exception as e:
        return jsonify({"error": f"Failed to fetch graph data: {str(e)}"}), 500
    finally:
        try:
            neo4j_session.close()
            driver.close()
        except:
            pass


@app.route('/analytics_page')
def analytics_page():
    if 'email' not in session:
        return redirect(url_for('login'))
    return render_template('analytics_page.html', username=session.get('username'))


@app.route('/chat-history')
def chat_history():
    if 'email' not in session:
        return jsonify({"error": "Please log in to view chat history."}), 401

    try:
        driver = connect_neo4j()
        neo4j_session = driver.session()

        chat_history = get_user_chat_history(session['email'], neo4j_session)
        return jsonify({"history": chat_history}), 200

    except Exception as e:
        print(f"Chat history error: {e}")
        return jsonify({"error": "Failed to retrieve chat history"}), 500
    finally:
        try:
            neo4j_session.close()
            driver.close()
        except:
            pass


# =====================================
# UTILITY FUNCTIONS
# =====================================

def get_graph_statistics(neo4j_session):
    """Get overall graph statistics"""
    query = """
    MATCH (n)
    RETURN labels(n) as node_types, count(*) as count
    """
    result = neo4j_session.run(query)

    node_stats = {}
    total_nodes = 0
    for record in result:
        node_type = record['node_types'][0] if record['node_types'] else 'Unknown'
        count = record['count']
        node_stats[node_type] = count
        total_nodes += count

    rel_query = """
    MATCH ()-[r]->()
    RETURN type(r) as rel_type, count(*) as count
    """
    rel_result = neo4j_session.run(rel_query)

    relationship_stats = {}
    total_relationships = 0
    for record in rel_result:
        rel_type = record['rel_type']
        count = record['count']
        relationship_stats[rel_type] = count
        total_relationships += count

    return {
        "total_nodes": total_nodes,
        "total_relationships": total_relationships,
        "node_distribution": node_stats,
        "relationship_distribution": relationship_stats
    }


def get_interaction_statistics(email, neo4j_session):
    """Get interaction statistics"""
    try:
        query = """
        MATCH (u:User {email: $email})-[:HAS_EPISODE]->(e:Episode)
        OPTIONAL MATCH (e)-[:HAS_INTERACTION]->(i:Interaction)
        OPTIONAL MATCH (i)-[:HAS_USER_RESPONSE]->(t:Text)
        RETURN 
            count(DISTINCT e) as total_episodes,
            count(DISTINCT i) as total_interactions,
            count(DISTINCT t) as total_user_responses
        """
        result = neo4j_session.run(query, email=email)
        record = result.single()

        if record:
            return {
                "total_interactions": record['total_interactions'],
                "total_episodes": record['total_episodes'],
                "total_user_responses": record['total_user_responses'],
                "recent_activity": []
            }
    except Exception as e:
        print(f"Interaction stats error: {e}")

    return {
        "total_interactions": 0,
        "total_episodes": 0,
        "total_user_responses": 0,
        "recent_activity": []
    }


if __name__ == "__main__":
    print("Starting Flask server with ESP32 standalone support...")
    print("Available endpoints:")
    print("  GET / - Home page")
    print("  GET/POST /login - Web login")
    print("  GET/POST /signup - Web signup")
    print("  POST /esp32_login - ESP32 login")
    print("  POST /esp32_signup - ESP32 signup")
    print("  POST /process_audio_chat - Basic audio processing")
    print("  POST /process_audio_chat_tts - Audio processing with TTS")
    print("  POST /esp32_audio_with_sensor - ESP32 audio with sensor data")
    print("  GET /download_tts - Download TTS audio")
    print("  GET /analytics - Analytics data")
    print("  GET /api/graph_data - Graph visualization")
    print("  GET /chat-history - Chat history")
    app.run(host='0.0.0.0', port=5001)
