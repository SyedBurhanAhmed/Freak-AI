import aiml
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from glob import glob
from nltk.corpus import wordnet as wn
from nltk import pos_tag, ne_chunk, sent_tokenize, word_tokenize
from nltk.tree import Tree
from nltk.sentiment import SentimentIntensityAnalyzer
import pytholog as pl
import calendar
from datetime import date
from neo4j import GraphDatabase
import hashlib
import re
import dns.resolver
from dateutil import parser
from datetime import datetime
import os
from pos_tags import pos_tags_dict
import requests
from threading import Thread
import uuid
from speech_recognition import Recognizer, Microphone, UnknownValueError, RequestError, WaitTimeoutError
import serial
import json
import threading
import time
import queue
import logging


mood = ""



class DHT11SensoryMemoryManager:
    def __init__(self, port='COM3', baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.serial_connection = None
        self.sensor_data = {
            'temperature': None,
            'humidity': None,
            'timestamp': None,
            'sensor_type': 'DHT11',
            'memory_type': 'SensoryMemory',
            'status': 'disconnected'
        }
        self.data_queue = queue.Queue(maxsize=100)
        self.running = False
        self.lock = threading.Lock()

        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        self.connect()

    def connect(self):
        """Connect to Arduino with retry logic"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self.serial_connection = serial.Serial(
                    self.port,
                    self.baudrate,
                    timeout=2,
                    write_timeout=2
                )
                time.sleep(2)  # Arduino initialization
                self.running = True
                self.sensor_data['status'] = 'connected'
                self.logger.info(f"Connected to DHT11 on {self.port}")

                # Start monitoring threads
                self.start_monitoring()
                return True

            except Exception as e:
                self.logger.error(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    self.sensor_data['status'] = 'error'
                    return False
                time.sleep(2)

    def start_monitoring(self):
        """Start background monitoring threads"""
        self.reader_thread = threading.Thread(target=self.read_sensor_data, daemon=True)
        self.processor_thread = threading.Thread(target=self.process_sensor_data, daemon=True)

        self.reader_thread.start()
        self.processor_thread.start()

    def read_sensor_data(self):
        """Continuous reading thread"""
        while self.running:
            try:
                if self.serial_connection and self.serial_connection.is_open:
                    self.serial_connection.write(b'GET_SENSOR_DATA\n')

                    response = self.serial_connection.readline().decode().strip()
                    if response:
                        try:
                            data = json.loads(response)
                            self.data_queue.put(data, timeout=1)
                        except json.JSONDecodeError:
                            self.logger.warning(f"Invalid JSON: {response}")

                time.sleep(30)  # Read every 30 seconds

            except Exception as e:
                self.logger.error(f"Read error: {e}")
                time.sleep(5)

    def process_sensor_data(self):
        """Process queued sensor data"""
        while self.running:
            try:
                data = self.data_queue.get(timeout=1)

                with self.lock:
                    if self.validate_sensor_data(data):
                        self.sensor_data.update(data)
                        self.sensor_data['python_timestamp'] = datetime.now().isoformat()

                        # Save to Neo4j as DHT11:SensoryMemory
                        threading.Thread(
                            target=self.save_dht11_sensory_memory,
                            args=(data.copy(),),
                            daemon=True
                        ).start()

                self.data_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Processing error: {e}")

    def validate_sensor_data(self, data):
        """Validate DHT11 sensor data ranges"""
        if not isinstance(data, dict):
            return False

        temp = data.get('temperature')
        humidity = data.get('humidity')

        # DHT11 specifications: 0-50°C, 20-80% RH
        if temp is not None and (temp < 0 or temp > 50):
            self.logger.warning(f"Temperature out of DHT11 range: {temp}")
            return False

        if humidity is not None and (humidity < 20 or humidity > 80):
            self.logger.warning(f"Humidity out of DHT11 range: {humidity}")
            return False

        return True

    def save_dht11_sensory_memory(self, sensor_data):
        """Optimized DHT11 data saving to prevent Cartesian products"""
        try:
            driver = connect_neo4j()
            if not driver:
                self.logger.warning("Neo4j not available, skipping sensor data save")
                return

            neo4j_session = driver.session()
            timestamp = datetime.now().isoformat()

            # Step 1: Create the sensor reading node
            neo4j_session.run("""
                CREATE (s:DHT11:SensoryMemory {
                    temperature: $temperature,
                    humidity: $humidity,
                    timestamp: $timestamp,
                    sensor_type: $sensor_type,
                    memory_type: $memory_type,
                    status: $status,
                    data_quality: $quality
                })
            """,
                              temperature=sensor_data.get('temperature'),
                              humidity=sensor_data.get('humidity'),
                              timestamp=timestamp,
                              sensor_type='DHT11',
                              memory_type='SensoryMemory',
                              status=sensor_data.get('status'),
                              quality='validated'
                              )

            # Step 2: Link to user (if available) using optimized query
            if hasattr(self, 'current_user_email') and self.current_user_email:
                neo4j_session.run("""
                    MERGE (u:User {email: $email})
                    WITH u
                    MATCH (s:DHT11:SensoryMemory {timestamp: $timestamp})
                    MERGE (u)-[:HAS_SENSOR_READING]->(s)
                """, email=self.current_user_email, timestamp=timestamp)

            neo4j_session.close()
            driver.close()

            self.logger.info(f"Saved DHT11:SensoryMemory - Temp: {sensor_data.get('temperature')}°C")

        except Exception as e:
            self.logger.warning(f"Neo4j save error: {e}")

    def set_current_user(self, email):
        """Set current user for sensor data linking"""
        self.current_user_email = email

    def get_latest_readings(self):
        """Thread-safe data access"""
        with self.lock:
            return self.sensor_data.copy()

    def get_environmental_context(self):
        """Get comprehensive environmental context"""
        with self.lock:
            data = self.sensor_data.copy()
            print(data)
            if data['status'] != 'valid':
                return None

            temp = data['temperature']
            humidity = data['humidity']
            print(temp, humidity)
            if temp is None or humidity is None:
                return None

            # Calculate comfort metrics
            comfort_score = self.calculate_comfort_score(temp, humidity)
            recommendations = self.get_recommendations(temp, humidity)
            print(comfort_score)
            return {
                'temperature': temp,
                'humidity': humidity,
                'comfort_level': comfort_score,
                'recommendations': recommendations,
                'timestamp': data.get('timestamp'),
                'sensor_type': 'DHT11',
                'memory_type': 'SensoryMemory'
            }

    def calculate_comfort_score(self, temp, humidity):
        """Calculate comfort score (0-100) based on DHT11 readings"""
        # Optimal ranges: 20-26°C temperature, 40-60% humidity
        temp_score = max(0, min(100, 100 - abs(temp - 23) * 10))
        humidity_score = max(0, min(100, 100 - abs(humidity - 50) * 2))
        return (temp_score + humidity_score) / 2

    def get_recommendations(self, temp, humidity):
        """Get environmental recommendations based on DHT11 readings"""
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
        if self.serial_connection:
            self.serial_connection.close()
        self.logger.info("DHT11 sensor manager disconnected")


# Initialize global sensor manager



def connect_neo4j():
    # Define the Neo4j connection details
    uri = "bolt://localhost:7687"
    username = "neo4j"
    password = "12345678@"
    # Create a Neo4j driver instance
    driver = GraphDatabase.driver(uri, auth=(username, password))
    return driver



def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def validate_data(email, password):
    driver = connect_neo4j()
    neo4j_session = driver.session()

    query = """
 MATCH (u:User{email:$email, password:$password})
 RETURN u
 """
    password = hash_password(password)
    user = neo4j_session.run(query, email=email, password=password).data()
    neo4j_session.close()
    driver.close()
    if user:
        return True

    return False


def check_email(email):
    driver = connect_neo4j()
    neo4j_session = driver.session()
    query = """
    MATCH (u:User{email:$email})
    RETURN u
    """
    user = neo4j_session.run(query, email=email).data()
    neo4j_session.close()
    driver.close()
    if user:
        print(user)
        return True
    return False


def is_valid_domain(email):
    domain = email.split("@")[1]
    try:
        dns.resolver.resolve(domain, 'MX')
        return True
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return False


def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_email(email):
    if is_valid_email(email) and is_valid_domain(email):
        return True
    return False


def get_username(email):
    driver = connect_neo4j()
    neo4j_session = driver.session()
    query = """
    MATCH (u:User{email: $email}) RETURN u.name
    """
    username = neo4j_session.run(query, email=email).data()[0]['u.name']
    neo4j_session.close()
    driver.close()
    return username


def store_credentials(name, email, password):
    password = hash_password(password)
    driver = connect_neo4j()
    neo4j_session = driver.session()

    query = """
    MERGE (u:User{name:$name, email:$email, password:$password})
    """
    neo4j_session.run(query, name=name, email=email, password=password)
    neo4j_session.close()
    driver.close()

    # Create empty facts file for the user
    fact_dir = "prolog/facts"
    os.makedirs(fact_dir, exist_ok=True)  # Ensure directory exists

    fact_path = os.path.join(fact_dir, f"{email.replace('@', '_at_')}.pl")
    with open(fact_path, "w") as f:
        f.write(f"% Facts for {email}\n")
        f.close()

    return


def sentiment_analysis(text):
    global mood
    sia = SentimentIntensityAnalyzer()
    results = sia.polarity_scores(text)
    if results['pos'] > results['neg']:
        myBot.setPredicate("sentiment", "positive")
        mood = "positive"
        return
    elif results['neg'] > results['pos']:
        myBot.setPredicate("sentiment", "negative")
        mood = "negative"
        return

    return


def check_sentiment(sentiment):
    pos = pos_tag([sentiment])
    entity = ne_chunk(pos)
    if isinstance(entity[0], Tree):  # Ensure it's a tree (named entity)
        entity_label = entity[0].label()
        if pos[0][1] == "NNP" and (entity_label == 'GPE' or entity_label == 'PERSON'):
            session_username = session.get('username', '')
            print(session_username)
            if check_name(sentiment, session_username):
                myBot.setPredicate("sentiment", "truth")
                print("Name is true")
            else:
                myBot.setPredicate("sentiment", "lie")
            return

    sentiment_analysis(sentiment)
    return


def set_sentiment():
    global mood
    sentiment = myBot.getPredicate("sentiment")
    if sentiment == "":
        myBot.setPredicate("sentiment", mood)
        return
    return


def get_description(word):
    description = '\n'
    sn = wn.synsets(word)
    length = len(sn)
    for i in range(length):
        # description += str(i+1)
        description += str(i + 1) + ". " + sn[i].definition()
        if i + 1 != length:
            description += '\n'

    return description


def check_meanings(word):
    if word == "":
        myBot.setPredicate("description", "I don't know.")
        return
    else:
        myBot.setPredicate("description", get_description(word))
        word = word.capitalize()
        myBot.setPredicate("word", word)
        return


def find_dob(person_name):
    person_name = person_name.lower() if person_name != "USER" else session["username"].lower()
    myBot.setPredicate("person", person_name.capitalize())
    query = f"dob({person_name}, (Y, M, D))"
    try:
        result = kb.query(pl.Expr(query))
        if result is None:
            result = ['No']
    except Exception as e:
        result = ['No']
    if result[0] != 'No':
        entry = result[0]  # pytholog returns a list of dicts
        raw_year = entry['Y']
        year = int(raw_year.replace('date', '').strip())
        month = int(entry['M'])
        day = int(entry['D'])

        # Convert month number to month name
        month_name = calendar.month_name[month]

        formatted_dob = f"{day} {month_name} {year}"
        myBot.setPredicate("dob", formatted_dob)
        myBot.setPredicate("dob_person", "")
        return
    else:
        myBot.setPredicate("dob", "unknown")
        myBot.setPredicate("dob_person", "")
        return


def find_age(person_name):
    person_name = person_name.lower() if person_name != "USER" else session["username"].lower()
    myBot.setPredicate("person", person_name.capitalize())
    query = f"dob({person_name}, (Y, M, D))"
    print(query)
    try:
        result = kb.query(pl.Expr(query))
        if result is None:
            result = ['No']
    except Exception as e:
        result = ['No']  # Assuming 'kb' is your pytholog KnowledgeBase object
    if result[0] != 'No':
        entry = result[0]
        raw_year = entry['Y']
        year = int(raw_year.replace('date', '').strip())
        month = int(entry['M'])
        day = int(entry['D'])

        today = date.today()
        age = today.year - year - ((today.month, today.day) < (month, day))
        myBot.setPredicate("age", str(age))  # Store age as string
        myBot.setPredicate("age_person", "")  # Clear old stored person if needed
        return
    else:
        myBot.setPredicate("age", "unknown")
        myBot.setPredicate("age_person", "")
        return





def find_gender(person_name):
    person_name = person_name.lower() if person_name != "USER" else session["username"].lower()
    myBot.setPredicate("person", person_name.capitalize())
    # First try male query
    query_male = pl.Expr(f"male({person_name})")
    try:
        result_male = kb.query(query_male)
        if result_male is None:
            result_male = ['No']
    except Exception as e:
        result_male = ['No']

    if result_male and result_male[0] != 'No':
        myBot.setPredicate("gender", "male")
        myBot.setPredicate("gender_person", person_name)
        return

    # If not male, try female query
    query_female = pl.Expr(f"female({person_name})")
    try:
        result_female = kb.query(query_female)
        if result_male is None:
            result_female = ['No']
    except Exception as e:
        result_female = ['No']

    if result_female and result_female[0] != 'No':
        myBot.setPredicate("gender", "female")
        myBot.setPredicate("gender_person", person_name)
        return

    # If neither male nor female found
    myBot.setPredicate("gender", "unknown")
    myBot.setPredicate("gender_person", person_name)
    return


def check_name(argument_name, session_username):
    """
    Check if the argument name matches the session username (partial match allowed)
    Returns True if name matches, False otherwise
    """
    if not argument_name or not session_username:
        return False

    # Convert both to lowercase for case-insensitive comparison
    arg_lower = argument_name.lower().strip()
    session_lower = session_username.lower().strip()

    # Split session username into individual names
    session_names = session_lower.split()

    # Check if argument matches any part of the session username
    for name_part in session_names:
        if arg_lower == name_part or name_part.startswith(arg_lower):
            return True

    # Check if argument is contained in the full session username
    if arg_lower in session_lower:
        return True

    return False


# Integration with AIML bot
def set_name_check_variable(argument_name, session):
    """
    Set the name_check variable in AIML based on name matching
    """
    session_username = session.get('username', '')

    if check_name(argument_name, session_username):
        myBot.setPredicate("name_check", "true")
        return True
    else:
        myBot.setPredicate("name_check", "false")
        print("Name is incorrect")
        return False


def prompt_check():
    username = session.get('username', '').lower()

    # Set current user for sensor data linking
    if 'email' in session:
        dht11_sensor.set_current_user(session['email'])

    keys = [
        "mood", "word", "dob_person", "age_person", "gender_person",
        "rel", "person1", "gender", "dob", "relation", "person",
        "other_dob_person", "other_dob", "other_gender_person", "other_gender",
        "other_person1", "other_person2", "other_relation", "delete", "user_input_name",
        "get_dht11_temperature", "get_dht11_humidity", "get_dht11_status",
        "analyze_dht11_environment", "get_dht11_memory"  # Added DHT11 predicates
    ]

    values = {key: myBot.getPredicate(key).strip() for key in keys}

    if values['user_input_name']:
        set_name_check_variable(values['user_input_name'],session)
    if values['delete']:
        delete_chat_history(session['email'])
    if values["word"]:
        check_meanings(values["word"])

    if values["mood"]:
        check_sentiment(values["mood"])

    if values["dob_person"]:
        find_dob(values["dob_person"])

    if values["age_person"]:
        print(values["age_person"])
        find_age(values["age_person"])

    if values["gender_person"]:
        print(values["gender_person"])
        find_gender(values["gender_person"])

    if values["rel"] or values["person1"]:
        check_relation(values["rel"], values["person1"])
    if values["other_person1"] and values["other_person2"] and values["other_relation"]:
        append_relation_fact(values["other_person1"], values["other_person2"] ,values["other_relation"])
    if values["gender"]:
        append_gender_fact(username, values["gender"])
    if values["other_gender_person"] and values["other_gender"]:
        append_gender_fact(values["other_gender_person"], values["other_gender"])
    if values["dob"]:
        append_dob_fact(username, values["dob"])
    if values["other_dob"] and values["other_dob_person"]:
        append_dob_fact(values["other_dob_person"], values["other_dob"])
    if values["relation"] == "married" and values["person1"]:
        append_relation_fact(username, values["person1"], values["relation"])
    if values["relation"] != "married" and values["person"]:
        append_relation_fact(username, values["person"], values["relation"])
        # Add DHT11 sensor handling
    if values["get_dht11_temperature"]:
        get_dht11_temperature()

    if values["get_dht11_humidity"]:
        get_dht11_humidity()

    if values["get_dht11_status"]:
        get_dht11_status()

    if values["analyze_dht11_environment"]:
        analyze_dht11_environment()

    if values["get_dht11_memory"]:
        memory_data = get_dht11_memory_data()
        if memory_data:
            latest = memory_data[0]
            myBot.setPredicate("latest_dht11_temp", str(latest['temperature']))
            myBot.setPredicate("latest_dht11_humidity", str(latest['humidity']))



def find_person(x, rel):
    expr = f"{rel}(Y,{x})"
    print(expr)
    try:
        result = kb.query(pl.Expr(expr))
        if result is None:
            result = ['No']
    except Exception as e:
        result = ['No']
    print(result)
    if result[0] != 'No':  # If result is not None or empty
        return result[0]["Y"]
    else:
        return "unknown"


def check_relation(rel,person1):
    rel = rel.lower()
    if rel == "" or person1 == "":
        return
    if person1 == "USER":
        person1 = session["username"].lower()
    if rel == "husband" or rel == "wife":
        rel = "married"
    person2 = find_person(person1,rel).capitalize()
    if person2 == "":
        myBot.setPredicate("person2", "unknown")
    else:
        myBot.setPredicate("person2", person2)
        return

def append_gender_fact(username, gender):
    fact = f"{gender.lower()}({username.lower()}).\n"  # example: male(burhan).

    print("Appending gender to Prolog file:", fact)

    fact_file_path = session.get("fact_file")  # get path from session

    if fact_file_path:
        with open(fact_file_path, "a") as f:  # 'a' mode for append
            f.write(fact)
            f.close()
    else:
        print("Fact file path not found in session.")



def append_dob_fact(username, dob):
    """
    Accepts natural date strings like:
    '12 nov 2024', '12 November 2024', '12/10/2024', '12-10-2024'
    and writes to fact file as: dob(username,date(YYYY,MM,DD)).
    """
    try:
        # Parse with dateutil (very flexible)
        date_obj = parser.parse(dob, dayfirst=True)  # dayfirst helps with DD/MM/YYYY format

        year, month, day = date_obj.year, date_obj.month, date_obj.day
        fact = f"dob({username.lower()},date({year},{month},{day})).\n"
        print("Appending to Prolog facts:", fact)

        # Append to fact file from session
        fact_file_path = session.get("fact_file")
        if fact_file_path:
            with open(fact_file_path, "a") as f:
                f.write(fact)
                f.close()
        else:
            print("Error: fact_file not found in session.")

    except Exception as e:
        print("Error parsing or writing DOB:", e)



def append_relation_fact(username, person1, relation):
    # --- Append to Prolog ---
    fact = f"{relation.lower()}({person1.lower()},{username.lower()}).\n"
    fact_file_path = session.get("fact_file")
    if fact_file_path:
        with open(fact_file_path, "a") as f:
            f.write(fact)

    # --- Trigger async Neo4j save using email from session ---
    user_email = session.get("email")
    if username:
        Thread(target=save_social_memory, args=(username,user_email, person1, relation)).start()
    else:
        print("[WARNING] No email found in session to save social memory.")

    return None



def save_social_memory(username, email, person1, relation):
    username_clean = username.strip().capitalize()
    person1_clean = person1.strip().capitalize()
    print(email)
    relation_upper = relation.upper().replace(" ", "_")
    if relation_upper in ["MARRIED", "SPOUSE", "WIFE", "HUSBAND", "PARTNER"]:
        edge_label = "IS_MARRIED_TO"
        is_bidirectional = True
    else:
        edge_label = f"IS_{relation_upper}_OF"
        is_bidirectional = False

    driver = connect_neo4j()
    neo4j_session = driver.session()

    try:
        # Ensure person1 node
        neo4j_session.run("""
            MERGE (p1:Person:SocialMemory {name: $person1})
        """, person1=person1_clean)
        if email != "":
            # Check if username is an existing user
            user_result = neo4j_session.run("""
                MATCH (u:User {email: $email})
                RETURN u.name AS uname
            """, email=email).single()

            uname = user_result["uname"] or username_clean
            neo4j_session.run("""
                MATCH (u:User {email: $email})
                
                SET u:Person:User:SocialMemory
            """, email=email)
        else:
            neo4j_session.run("""
                CREATE (u:Person:SocialMemory {name: $uname})
            """, uname=username_clean)
        print("yahan tak theek hai")
        # Relationship creation
        if is_bidirectional:
            query = f"""
                MATCH (p1:Person {{name: $person1}}), (p2:User {{email: $email}})
                MERGE (p1)-[:{edge_label}]->(p2)
                MERGE (p2)-[:{edge_label}]->(p1)
            """
            neo4j_session.run(query, person1=person1_clean, email=email)
            print("bi directional query chalgyi")
        else:
            query = f"""
                MATCH (p1:Person {{name: $person1}}), (p2:User {{email: $email}})
                MERGE (p1)-[:{edge_label}]->(p2)
            """
            neo4j_session.run(query, person1=person1_clean, email=email)
            print("uni directional query chalgyi")



    except Exception as e:
        print(f"[NEO4J ERROR]: {e}")
    finally:
        neo4j_session.close()
        driver.close()



def save_sensory_memory(text, timestamp=None):
    if timestamp is None:
        timestamp = datetime.now().isoformat()
    ip_address = get_public_ip()

    driver = connect_neo4j()
    neo4j_session = driver.session()

    neo4j_session.run("""
        MERGE (t:Text:SensoryMemory {full_text: $text, timestamp: $timestamp, ip_address: $ip_address})
    """, text=text, timestamp=timestamp, ip_address=ip_address)
    sentences = sent_tokenize(text)
    prev_sentence = None
    for sentence in sentences:
        neo4j_session.run("""
            MATCH (t:Text:SensoryMemory {full_text: $text})
            MERGE (s:Sentence:SensoryMemory {sentence_text: $sentence})
            MERGE (t)-[:HAS_A_SENTENCE]->(s)
        """, text=text, sentence=sentence)
        if prev_sentence:
            neo4j_session.run("""
                MATCH (s1:Sentence {sentence_text: $prev_sentence}), (s2:Sentence {sentence_text: $curr_sentence})
                MERGE (s1)-[:NEXT_SENTENCE]->(s2)
            """, prev_sentence=prev_sentence, curr_sentence=sentence)
        prev_sentence = sentence
        words = word_tokenize(sentence)
        prev_word = None
        for word in words:
            neo4j_session.run("""
                MATCH (s:Sentence {sentence_text: $sentence})
                MERGE (w:Word:SensoryMemory {word_text: $word})
                MERGE (s)-[:HAS_A_WORD]->(w)
            """, sentence=sentence, word=word)
            if prev_word:
                neo4j_session.run("""
                    MATCH (w1:Word {word_text: $prev_word}), (w2:Word {word_text: $curr_word})
                    MERGE (w1)-[:NEXT_WORD]->(w2)
                """, prev_word=prev_word, curr_word=word)
            prev_word = word
    neo4j_session.close()
    driver.close()



def get_wordnet_pos(treebank_tag):
    if treebank_tag.startswith('J'):
        return wn.ADJ
    elif treebank_tag.startswith('V'):
        return wn.VERB
    elif treebank_tag.startswith('N'):
        return wn.NOUN
    elif treebank_tag.startswith('R'):
        return wn.ADV
    else:
        return None



def save_semantic_memory(text):
    from nltk.corpus import wordnet as wn
    words = word_tokenize(text)
    tagged_words = pos_tag(words)
    driver = connect_neo4j()
    neo4j_session = driver.session()
    for word, tag in tagged_words:
        wn_pos = get_wordnet_pos(tag)
        if wn_pos:
            synsets = wn.synsets(word, pos=wn_pos)
            if synsets:
                synset = synsets[0]
                definition = synset.definition()
                synonyms = set(lemma.name() for lemma in synset.lemmas())
                antonyms = set(ant.name() for lemma in synset.lemmas() for ant in lemma.antonyms())
                neo4j_session.run("""
                    MERGE (d:Description:SemanticMemory {description: $definition})
                    WITH d MATCH (w:Word:SensoryMemory {word_text: $word})
                    MERGE (w)-[:IS_A]->(d)
                """, word=word, definition=definition)
                for synonym in synonyms:
                    neo4j_session.run("""
                        MERGE (s:Synonym:SemanticMemory {synonym: $synonym})
                        WITH s MATCH (w:Word:SensoryMemory {word_text: $word})
                        MERGE (w)-[:HAS_SYNONYM]->(s)
                    """, word=word, synonym=synonym)
                for antonym in antonyms:
                    neo4j_session.run("""
                        MERGE (a:Antonym:SemanticMemory {antonym: $antonym})
                        WITH a MATCH (w:Word:SensoryMemory {word_text: $word})
                        MERGE (w)-[:HAS_ANTONYM]->(a)
                    """, word=word, antonym=antonym)
                hypernyms = synset.hypernyms()
                if hypernyms:
                    hyper = hypernyms[0].lemmas()[0].name()
                    neo4j_session.run("""
                        MERGE (c:Category:SemanticMemory {name: $hypernym})
                        WITH c MATCH (w:Word:SensoryMemory {word_text: $word})
                        MERGE (w)-[:IS_A]->(c)
                    """, word=word, hypernym=hyper)
                domain = synset.lexname().split(".")[-1]
                neo4j_session.run("""
                    MERGE (d:Domain:SemanticMemory {domain_name: $domain})
                    WITH d MATCH (w:Word:SensoryMemory {word_text: $word})
                    MERGE (w)-[:BELONGS_TO_DOMAIN]->(d)
                """, word=word, domain=domain)
    neo4j_session.close()
    driver.close()

def extract_named_entities_from_words(words):
    named_entities = []
    pos = pos_tag(words)
    ne_tree = ne_chunk(pos)
    for subtree in ne_tree:
        if isinstance(subtree, Tree):
            entity_name = " ".join([token for token, _ in subtree.leaves()])
            entity_type = subtree.label()
            named_entities.append((entity_name, entity_type))
    return named_entities


def classify_sentence_type(sentence):
    words = word_tokenize(sentence)
    tags = pos_tag(words)

    if not words:
        return "unknown"

    first_word = words[0].lower()
    first_tag = tags[0][1] if tags else ""

    # Interrogative if sentence starts with wh-word or auxiliary/modal verb
    wh_words = {"what", "when", "where", "who", "why", "how", "which", "whom", "whose"}
    aux_modals = {"is", "are", "was", "were", "do", "does", "did", "can", "could", "will", "would", "should", "shall", "may", "might", "have", "has", "had"}

    if first_word in wh_words or first_word in aux_modals:
        return "interrogative"

    # Imperative: usually starts with base form verb (VB) and no subject (PRP/NOUN)
    if first_tag == "VB" and all(tag[1] not in {"PRP", "NN", "NNP"} for tag in tags[:2]):
        return "imperative"

    # Exclamatory: begins with interjection (UH) or exclamatory adjective/adverb
    if first_tag == "UH" or first_word in {"what", "how"} and len(tags) > 1 and tags[1][1] in {"JJ", "RB"}:
        return "exclamatory"

    # Default fallback
    return "declarative"

def get_public_ip():
    try:
        return requests.get("https://api.ipify.org").text
    except:
        return "Unknown"

def get_location_from_ip(ip=get_public_ip()):
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}")
        data = response.json()

        return data.get("city", "Unknown"), data.get("country", "Unknown")
    except:
        return "Unknown", "Unknown"

def save_pam_from_sensory_memory(text):
    driver = connect_neo4j()
    neo4j_session = driver.session()
    sia = SentimentIntensityAnalyzer()
    ip_address = get_public_ip()
    city, country = get_location_from_ip(ip_address)

    sentences = sent_tokenize(text)

    for sentence in sentences:
        result = neo4j_session.run("""
            MATCH (s:Sentence:SensoryMemory {sentence_text: $sentence})
            RETURN s
        """, sentence=sentence)

        if result.peek() is None:
            print(f"[SKIPPED] Sentence not found in sensory memory: {sentence}")
            continue

        # Sentiment
        sentiment_score = sia.polarity_scores(sentence)
        neo4j_session.run("""
            MERGE (se:Sentiment:PerceptualAssociativeMemory {
                positive: $positive,
                negative: $negative,
                neutral: $neutral,
                compound: $compound
            })
            WITH se MATCH (s:Sentence:SensoryMemory {sentence_text: $sentence})
            MERGE (s)-[:HAS_SENTIMENT]->(se)
        """, sentence=sentence,
             positive=sentiment_score["pos"],
             negative=sentiment_score["neg"],
             neutral=sentiment_score["neu"],
             compound=sentiment_score["compound"])

        # Mood node based on dominant sentiment
        if sentiment_score["pos"] > sentiment_score["neg"] and sentiment_score["pos"] > sentiment_score["neu"]:
            mood = "positive"
        elif sentiment_score["neg"] > sentiment_score["pos"] and sentiment_score["neg"] > sentiment_score["neu"]:
            mood = "negative"
        else:
            mood = "neutral"
        neo4j_session.run("""
            MERGE (m:Mood:PerceptualAssociativeMemory {mood: $mood})
            WITH m MATCH (s:Sentence:SensoryMemory {sentence_text: $sentence})
            MERGE (s)-[:HAS_MOOD]->(m)
        """, sentence=sentence, mood=mood)

        # Sentence Type
        sentence_type = classify_sentence_type(sentence)
        neo4j_session.run("""
            MERGE (t:SentenceType:PerceptualAssociativeMemory {type: $type})
            WITH t MATCH (s:Sentence:SensoryMemory {sentence_text: $sentence})
            MERGE (s)-[:HAS_TYPE]->(t)
        """, sentence=sentence, type=sentence_type)

        # IP + Location
        neo4j_session.run("""
            MERGE (ip:IPAddress:PerceptualAssociativeMemory {ip: $ip})
            MERGE (loc:Location:PerceptualAssociativeMemory {city: $city, country: $country})
            WITH ip, loc
            MATCH (s:Sentence:SensoryMemory {sentence_text: $sentence})
            MERGE (s)-[:ORIGINATED_FROM]->(ip)
            MERGE (ip)-[:GEO_LOCATED_AT]->(loc)
        """, sentence=sentence, ip=ip_address, city=city, country=country)

        # POS Tags and Named Entities as attributes of Word node
        words = word_tokenize(sentence)
        pos_tags = pos_tag(words)
        named_entities = extract_named_entities_from_words(words)
        entity_map = {word: entity_type for word, entity_type in named_entities}

        for word, pos in pos_tags:
            long_pos = pos_tags_dict.get(pos, "Unknown")
            named_entity = entity_map.get(word) or "None"
            neo4j_session.run("""
                MERGE (w:Word:SensoryMemory:PerceptualAssociativeMemory {
                    word_text: $word,
                    pos_tag: $pos,
                    pos_tag_long: $long_pos,
                    named_entity: $named_entity
                })
                WITH w MATCH (s:Sentence:SensoryMemory {sentence_text: $sentence})
                MERGE (s)-[:HAS_A_WORD]->(w)
            """, word=word, pos=pos, long_pos=long_pos, named_entity=named_entity, sentence=sentence)

    neo4j_session.close()
    driver.close()



def get_session_id(session):
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return session['session_id']

def create_episode(user_email, session):
    session_id = get_session_id(session)
    start_time = datetime.now().isoformat()
    driver = connect_neo4j()
    neo4j_session = driver.session()
    # Find previous episode for this user
    prev_episode = neo4j_session.run("""
        MATCH (u:User {email: $email})-[:HAS_EPISODE]->(e:Episode)
        RETURN e ORDER BY e.start_time DESC LIMIT 1
    """, email=user_email).single()
    # Create new episode
    neo4j_session.run("""
        MERGE (u:User {email: $email})
        CREATE (ep:Episode:EpisodicMemory {session_id: $session_id, start_time: $start_time})
        MERGE (u)-[:HAS_EPISODE]->(ep)
    """, email=user_email, session_id=session_id, start_time=start_time)
    # Chain episodes
    if prev_episode:
        prev_id = prev_episode['e']['session_id']
        neo4j_session.run("""
            MATCH (e1:Episode {session_id: $prev_id}), (e2:Episode {session_id: $curr_id})
            MERGE (e1)-[:NEXT_EPISODE]->(e2)
        """, prev_id=prev_id, curr_id=session_id)
    neo4j_session.close()
    driver.close()
    session['current_episode_id'] = session_id

def end_episode(user_email, session):
    session_id = session.get('current_episode_id')
    if not session_id:
        return
    end_time = datetime.now().isoformat()
    driver = connect_neo4j()
    neo4j_session = driver.session()
    neo4j_session.run("""
        MATCH (e:Episode {session_id: $session_id})
        SET e.end_time = $end_time
    """, session_id=session_id, end_time=end_time)
    neo4j_session.close()
    driver.close()
    session.pop('current_episode_id', None)
    session.pop('session_id', None)


def create_interaction(user_email, user_input, bot_output, session):

    interaction_id = str(uuid.uuid4())
    session_id = session.get('current_episode_id','esp')
    if not session_id:
        return

    # Generate timestamps once so they're consistent across sensory + link
    user_time = datetime.now().isoformat()
    bot_time = datetime.now().isoformat()

    # Save both texts to memory systems first
    save_sensory_memory(user_input, timestamp=user_time)
    save_semantic_memory(user_input)
    save_pam_from_sensory_memory(user_input)

    save_sensory_memory(bot_output, timestamp=bot_time)
    save_semantic_memory(bot_output)
    save_pam_from_sensory_memory(bot_output)

    # Begin Neo4j operations
    driver = connect_neo4j()
    neo4j_session = driver.session()

    # Ensure agent node exists
    neo4j_session.run("""
        MERGE (a:Agent {name: 'Freak'})
    """)

    # Ensure user is linked to episode
    neo4j_session.run("""
        MATCH (u:User {email: $user_email}), (e:Episode {session_id: $session_id})
        MERGE (u)-[:HAS_EPISODE]->(e)
    """, user_email=user_email, session_id=session_id)

    # --- FIND PREVIOUS INTERACTION BEFORE CREATING NEW ---
    prev_interaction = neo4j_session.run("""
        MATCH (e:Episode {session_id: $session_id})-[:HAS_INTERACTION]->(prev:Interaction)
        WHERE NOT (prev)-[:NEXT_INTERACTION]->()
        RETURN prev ORDER BY prev.timestamp DESC LIMIT 1
    """, session_id=session_id).single()

    # --- CREATE NEW INTERACTION ---
    neo4j_session.run("""
        MATCH (e:Episode {session_id: $session_id})
        CREATE (i:Interaction:EpisodicMemory {
            interaction_id: $interaction_id,
            timestamp: $timestamp,
            user_email: $user_email
        })
        MERGE (e)-[:HAS_INTERACTION]->(i)
    """, interaction_id=interaction_id, timestamp=user_time, user_email=user_email, session_id=session_id)

    # --- NOW CREATE NEXT_INTERACTION LINK ---
    if prev_interaction:
        prev_id = prev_interaction['prev']['interaction_id']
        neo4j_session.run("""
            MATCH (i1:Interaction {interaction_id: $prev_id}), (i2:Interaction {interaction_id: $curr_id})
            MERGE (i1)-[:NEXT_INTERACTION]->(i2)
        """, prev_id=prev_id, curr_id=interaction_id)

    # Link user response to interaction
    neo4j_session.run("""
        MATCH (i:Interaction {interaction_id: $interaction_id}),
              (t:Text:SensoryMemory {full_text: $text, timestamp: $timestamp})
        MERGE (i)-[:HAS_USER_RESPONSE]->(t)
    """, interaction_id=interaction_id, text=user_input, timestamp=user_time)

    # Link bot response to interaction and agent
    neo4j_session.run("""
        MATCH (i:Interaction {interaction_id: $interaction_id}),
              (t:Text:SensoryMemory {full_text: $text, timestamp: $timestamp}),
              (a:Agent {name: 'Freak'})
        MERGE (i)-[:HAS_BOT_RESPONSE]->(t)
        MERGE (a)-[:GENERATED]->(t)
    """, interaction_id=interaction_id, text=bot_output, timestamp=bot_time)

    neo4j_session.close()
    driver.close()

def async_create_interaction(user_email, user_input, bot_output, session_snapshot):
    try:
        # call create_interaction with a copy of session (dict only!)
        create_interaction(user_email, user_input, bot_output, session_snapshot)
        print("Interaction created")
    except Exception as e:
        print(f"[ASYNC INTERACTION ERROR]: {e}")





def get_user_statistics(email, neo4j_session):
    """Get user-specific statistics"""
    try:
        query = """
        MATCH (u:User {email: $email})
        OPTIONAL MATCH (u)-[:HAS_EPISODE]->(e:Episode)
        OPTIONAL MATCH (e)-[:HAS_INTERACTION]->(i:Interaction)
        RETURN 
            count(DISTINCT e) as episode_count,
            count(DISTINCT i) as interaction_count
        """
        result = neo4j_session.run(query, email=email)
        record = result.single()

        if record:
            return {
                "total_memories": record['episode_count'],
                "total_interactions": record['interaction_count']
            }
    except Exception as e:
        print(f"User stats error: {e}")

    return {"total_memories": 0, "total_interactions": 0}


def get_memory_statistics(email, neo4j_session):
    """Get memory-related statistics with correct relationship names"""
    try:
        query = """
        MATCH (u:User {email: $email})-[:HAS_EPISODE]->(e:Episode)
        OPTIONAL MATCH (e)-[:HAS_INTERACTION]->(i:Interaction)
        OPTIONAL MATCH (i)-[:HAS_USER_RESPONSE]->(t:Text)
        OPTIONAL MATCH (t)-[:HAS_A_SENTENCE]->(s:Sentence)
        OPTIONAL MATCH (s)-[:HAS_A_WORD]->(w:Word)
        RETURN 
            count(DISTINCT e) as episode_count,
            count(DISTINCT t) as text_count,
            count(DISTINCT s) as sentence_count,
            count(DISTINCT w) as word_count
        """
        result = neo4j_session.run(query, email=email)
        record = result.single()

        if record:
            return {
                "total_memories": record['episode_count'],
                "total_sentences": record['sentence_count'],
                "total_words": record['word_count']  # This should now work
            }
    except Exception as e:
        print(f"Memory stats error: {e}")

    return {"total_memories": 0, "total_sentences": 0, "total_words": 0}


def get_complete_graph_statistics(neo4j_session):
    """Get complete graph statistics - simplified and efficient"""
    try:
        # Get all nodes with their labels
        nodes_query = """
        MATCH (n)
        RETURN labels(n) as node_types, count(*) as count
        """
        result = neo4j_session.run(nodes_query)

        node_stats = {}
        total_nodes = 0
        for record in result:
            node_type = record['node_types'][0] if record['node_types'] else 'Unknown'
            count = record['count']
            node_stats[node_type] = count
            total_nodes += count

        # Get all relationships with their types
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

    except Exception as e:
        print(f"Graph stats error: {e}")
        return {
            "total_nodes": 0,
            "total_relationships": 0,
            "node_distribution": {},
            "relationship_distribution": {}
        }


def get_user_chat_history(email, session):
    """Retrieve complete chat history for a user from Neo4j"""
    try:
        driver = connect_neo4j()
        neo4j_session = driver.session()

        query = """
        MATCH (u:User {email: $email})-[:HAS_EPISODE]->(e:Episode)
        MATCH (e)-[:HAS_INTERACTION]->(i:Interaction)
        OPTIONAL MATCH (i)-[:HAS_USER_RESPONSE]->(ur:Text)
        OPTIONAL MATCH (i)-[:HAS_BOT_RESPONSE]->(br:Text)
        RETURN 
            e.start_time as episode_start,
            e.end_time as episode_end,
            i.interaction_id as interaction_id,
            ur.full_text as user_message,
            br.full_text as bot_response,
            u.name as username
        ORDER BY e.start_time DESC, i.interaction_id
        """

        result = neo4j_session.run(query, email=email)

        # Process results into structured chat history
        chat_history = []
        current_episode = None

        for record in result:
            episode_start = record['episode_start']
            episode_end = record['episode_end']
            username = record['username'] or 'User'
            user_message = record['user_message']
            bot_response = record['bot_response']

            # Create new episode if it doesn't exist
            if current_episode is None or current_episode['episode_start'] != episode_start:
                # Extract date and time from ISO timestamp
                try:
                    from datetime import datetime
                    start_dt = datetime.fromisoformat(episode_start)
                    episode_date = start_dt.strftime('%Y-%m-%d')
                    episode_time = start_dt.strftime('%H:%M:%S')

                    # Calculate duration if end time exists
                    duration = 'Ongoing'
                    session_status = 'active'

                    if episode_end:
                        end_dt = datetime.fromisoformat(episode_end)
                        duration_seconds = (end_dt - start_dt).total_seconds()
                        hours = int(duration_seconds // 3600)
                        minutes = int((duration_seconds % 3600) // 60)
                        seconds = int(duration_seconds % 60)

                        if hours > 0:
                            duration = f"{hours}h {minutes}m {seconds}s"
                        elif minutes > 0:
                            duration = f"{minutes}m {seconds}s"
                        else:
                            duration = f"{seconds}s"

                        session_status = 'completed'

                    episode_title = f"{episode_date} at {episode_time}"

                except Exception as e:
                    print(f"Error parsing timestamp: {e}")
                    episode_date = episode_start
                    episode_time = ""
                    episode_title = f"Session {episode_start[:10]}"
                    duration = 'Unknown'
                    session_status = 'unknown'

                current_episode = {
                    'episode_start': episode_start,
                    'episode_end': episode_end,
                    'episode_date': episode_date,
                    'episode_time': episode_time,
                    'session_status': session_status,
                    'session_duration': duration,
                    'episode_title': episode_title,
                    'conversations': []
                }
                chat_history.append(current_episode)

            # Add conversation pair if both messages exist
            if user_message and bot_response:
                conversation = {
                    'user_message': f"{username}: {user_message}",
                    'bot_response': f"Freak: {bot_response}"
                }
                current_episode['conversations'].append(conversation)

        return chat_history

    except Exception as e:
        print(f"Error retrieving chat history: {e}")
        return []
    finally:
        try:
            neo4j_session.close()
            driver.close()
        except:
            pass

def delete_chat_history(user_email):
    """Delete all memory-related nodes for a specific user from Neo4j"""
    try:
        driver = connect_neo4j()
        neo4j_session = driver.session()

        # Count nodes before deletion for the specific user
        count_query = """
        MATCH (u:User {email: $email})-[:HAS_EPISODE]->(e:Episode)
        MATCH (e)-[:HAS_INTERACTION]->(i:Interaction)
        OPTIONAL MATCH (i)-[:HAS_USER_RESPONSE|HAS_BOT_RESPONSE]->(t:Text)
        OPTIONAL MATCH (t)-[:HAS_A_SENTENCE]->(s:Sentence)
        OPTIONAL MATCH (s)-[:HAS_A_WORD]->(w:Word)
        OPTIONAL MATCH (n) WHERE (
            'EpisodicMemory' IN labels(n) OR 
            'SensoryMemory' IN labels(n) OR
            'PerceptualAssociativeMemory' IN labels(n) OR
            'SemanticMemory' IN labels(n) OR
            'SocialMemory' IN labels(n)
        ) AND (
            (u)-[:HAS_EPISODE*1..10]->(n) OR
            (e)-[:HAS_INTERACTION*1..10]->(n) OR
            (i)-[:HAS_USER_RESPONSE|HAS_BOT_RESPONSE*1..10]->(n) OR
            (t)-[:HAS_A_SENTENCE*1..10]->(n) OR
            (s)-[:HAS_A_WORD*1..10]->(n)
        )
        RETURN count(DISTINCT e) + count(DISTINCT i) + count(DISTINCT t) + 
               count(DISTINCT s) + count(DISTINCT w) + count(DISTINCT n) as nodes_to_delete
        """

        result = neo4j_session.run(count_query, email=user_email)
        count = result.single()['nodes_to_delete']
        print(f"Found {count} memory nodes to delete for user {user_email}")

        # Delete episodes and all connected memory nodes for the specific user
        delete_episodes_query = """
        MATCH (u:User {email: $email})-[:HAS_EPISODE]->(e:Episode)
        DETACH DELETE e
        """

        # Delete interactions and all connected memory nodes for the specific user
        delete_interactions_query = """
        MATCH (u:User {email: $email})-[:HAS_EPISODE]->(e:Episode)
        MATCH (e)-[:HAS_INTERACTION]->(i:Interaction)
        DETACH DELETE i
        """

        # Delete text nodes and all connected memory nodes for the specific user
        delete_text_query = """
        MATCH (u:User {email: $email})-[:HAS_EPISODE]->(e:Episode)
        MATCH (e)-[:HAS_INTERACTION]->(i:Interaction)
        MATCH (i)-[:HAS_USER_RESPONSE|HAS_BOT_RESPONSE]->(t:Text)
        DETACH DELETE t
        """

        # Delete sentences and all connected memory nodes for the specific user
        delete_sentences_query = """
        MATCH (u:User {email: $email})-[:HAS_EPISODE]->(e:Episode)
        MATCH (e)-[:HAS_INTERACTION]->(i:Interaction)
        MATCH (i)-[:HAS_USER_RESPONSE|HAS_BOT_RESPONSE]->(t:Text)
        MATCH (t)-[:HAS_A_SENTENCE]->(s:Sentence)
        DETACH DELETE s
        """

        # Delete words and all connected memory nodes for the specific user
        delete_words_query = """
        MATCH (u:User {email: $email})-[:HAS_EPISODE]->(e:Episode)
        MATCH (e)-[:HAS_INTERACTION]->(i:Interaction)
        MATCH (i)-[:HAS_USER_RESPONSE|HAS_BOT_RESPONSE]->(t:Text)
        MATCH (t)-[:HAS_A_SENTENCE]->(s:Sentence)
        MATCH (s)-[:HAS_A_WORD]->(w:Word)
        DETACH DELETE w
        """

        # Delete specific memory type nodes connected to the user
        delete_memory_nodes_query = """
        MATCH (u:User {email: $email})
        MATCH (u)-[:HAS_EPISODE*1..10]->(n)
        WHERE 'EpisodicMemory' IN labels(n) OR 
              'SensoryMemory' IN labels(n) OR
              'PerceptualAssociativeMemory' IN labels(n) OR
              'SemanticMemory' IN labels(n) OR
              'SocialMemory' IN labels(n)
        DETACH DELETE n
        """

        # Execute deletions in reverse order (from leaves to root)
        neo4j_session.run(delete_words_query, email=user_email)
        neo4j_session.run(delete_sentences_query, email=user_email)
        neo4j_session.run(delete_text_query, email=user_email)
        neo4j_session.run(delete_interactions_query, email=user_email)
        neo4j_session.run(delete_memory_nodes_query, email=user_email)
        neo4j_session.run(delete_episodes_query, email=user_email)

        print(f"Successfully deleted {count} memory nodes for user {user_email}")
        print("User account preserved")

    except Exception as e:
        print(f"Error deleting memory nodes: {e}")
    finally:
        try:
            neo4j_session.close()
            driver.close()
        except:
            pass


def get_dht11_temperature():
    """Get current temperature from DHT11 sensor"""
    temp = dht11_sensor.get_latest_readings().get('temperature')
    print(temp)
    if temp is not None:
        myBot.setPredicate("dht11_temperature", str(temp))
        myBot.setPredicate("dht11_temp_unit", "°C")
        myBot.setPredicate("sensor_type", "DHT11")
    else:
        myBot.setPredicate("dht11_temperature", "unavailable")
    return temp


def get_dht11_humidity():
    """Get current humidity from DHT11 sensor"""
    humidity = dht11_sensor.get_latest_readings().get('humidity')
    print(humidity)
    if humidity is not None:
        myBot.setPredicate("dht11_humidity", str(humidity))
        myBot.setPredicate("dht11_humidity_unit", "%")
        myBot.setPredicate("sensor_type", "DHT11")
    else:
        myBot.setPredicate("dht11_humidity", "unavailable")
    return humidity


def get_dht11_status():
    """Get DHT11 sensor status"""
    data = dht11_sensor.get_latest_readings()
    print("dht status: ", data)
    status = data['status']
    myBot.setPredicate("dht11_status", status)
    myBot.setPredicate("sensor_type", "DHT11")
    return status


def analyze_dht11_environment():
    """Analyze environment using DHT11 readings"""
    context = dht11_sensor.get_environmental_context()
    print(context)
    if context:
        myBot.setPredicate("dht11_comfort_score", str(int(context['comfort_level'])))
        myBot.setPredicate("dht11_recommendations", "; ".join(context['recommendations']))
        myBot.setPredicate("environmental_status", "analyzed")
    else:
        myBot.setPredicate("environmental_status", "unavailable")

    return context


def get_dht11_memory_data():
    """Get recent DHT11 sensory memory data from Neo4j"""
    try:
        driver = connect_neo4j()
        neo4j_session = driver.session()

        # Get recent DHT11 readings
        query = """
        MATCH (s:DHT11:SensoryMemory)
        RETURN s.temperature as temp, s.humidity as humidity, s.timestamp as timestamp
        ORDER BY s.timestamp DESC
        LIMIT 5
        """

        result = neo4j_session.run(query)
        readings = []

        for record in result:
            readings.append({
                'temperature': record['temp'],
                'humidity': record['humidity'],
                'timestamp': record['timestamp']
            })

        neo4j_session.close()
        driver.close()

        return readings

    except Exception as e:
        print(f"Error retrieving DHT11 memory data: {e}")
        return []


recognizer = Recognizer()


def recognize_speech():
    with Microphone() as source:
        print("Listening for speech...")
        recognizer.adjust_for_ambient_noise(source)
        audio = recognizer.listen(source, timeout=3)

        try:
            text = recognizer.recognize_google(audio)
            print(f"Recognized text: {text}")
            return text
        except WaitTimeoutError:
            print("Listening timed out while waiting for speech.")
            return "timeout"
        except UnknownValueError:
            return None
        except RequestError:
            return None
    return None


kb = pl.KnowledgeBase("family")
kb.clear_cache()
kb.from_file("prolog/kb.pl")

myBot = aiml.Kernel()
app = Flask(__name__)
app.secret_key = 'your-secret-key'
aiml_files = glob("aiml files/*.aiml")
for file in aiml_files:
    myBot.learn(file)


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


@app.route('/transcribe', methods=['GET'])
def transcribe_speech():
    try:
        query = recognize_speech()

        if query == "timeout":
            return jsonify({"error": "Listening timed out. Please try again."}), 408
        elif not query:
            return jsonify({"error": "Could not understand speech"}), 400

        return jsonify({"query": query}), 200

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return jsonify({"error": "An unexpected error occurred. Please try again."}), 500


# Updated route to handle both GET and POST requests
@app.route("/get", methods=['GET', 'POST'])
def get_bot_response():
    if "email" not in session:
        return jsonify({"error": "Please log in to use the bot."}), 401

    kb.from_file(session["fact_file"])

    # Handle both GET and POST requests
    if request.method == 'POST':
        data = request.get_json()
        query = data.get('msg') if data else None
    else:
        query = request.args.get('msg')

    if not query:
        return jsonify({"error": "No message provided"}), 400

    try:
        # Process the query
        myBot.respond(query)
        prompt_check()
        response = myBot.respond(query)

        # Async interaction logging
        session_snapshot = dict(session)
        Thread(target=async_create_interaction, args=(session["email"], query, response, session_snapshot)).start()

        set_sentiment()

        # Clear predicates
        for key in [
            "mood", "word", "dob_person", "age_person", "gender_person",
            "rel", "person1", "gender", "dob", "relation", "person",
            "other_dob_person", "other_dob", "other_gender_person", "other_gender",
            "other_person1", "other_person2", "other_relation","delete","user_input_name"
        ]:
            myBot.setPredicate(key, "")

        return jsonify({"response": response}), 200

    except Exception as e:
        print(f"Error processing message: {e}")
        return jsonify({"error": "Sorry, I encountered an error processing your message."}), 500


# New routes for dashboard functionality
@app.route('/analytics')
def analytics():
    if 'email' not in session:
        return jsonify({"error": "Please log in to view analytics."}), 401

    try:
        driver = connect_neo4j()
        neo4j_session = driver.session()

        # Get comprehensive analytics data
        analytics_data = {
            "user_stats": get_user_statistics(session['email'], neo4j_session),
            "graph_stats": get_complete_graph_statistics(neo4j_session),  # Updated function
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
    """API endpoint to fetch complete Neo4j graph data for visualization"""
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

            # Create display label from actual properties
            display_label = ""
            if 'name' in properties:
                display_label = properties['name']
            elif 'email' in properties:
                display_label = properties['email']
            elif 'sentence_text' in properties:
                display_label = properties['sentence_text'][:50] + "..." if len(properties['sentence_text']) > 50 else properties['sentence_text']
            elif 'full_text' in properties:
                display_label = properties['full_text'][:30] + "..." if len(properties['full_text']) > 30 else properties['full_text']
            elif 'word_text' in properties:
                display_label = properties['word_text']
            elif 'session_id' in properties:
                display_label = f"Episode {properties['session_id'][:8]}"
            elif 'interaction_id' in properties:
                display_label = f"Interaction {properties['interaction_id'][:8]}"
            else:
                display_label = f"{labels[0] if labels else 'Node'}"

            # Color coding based on node type
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

        # Format edges for visualization
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

        # Get chat history for the logged-in user
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

    # Get relationship statistics
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
    """Get interaction statistics based on actual schema"""
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


@app.route('/logout')
def logout():
    if "email" in session:
        end_episode(session["email"], session)
    session.clear()
    return redirect(url_for('login'))


if __name__ == "__main__":
    dht11_sensor = DHT11SensoryMemoryManager()
    app.run(host='0.0.0.0', port='5001')