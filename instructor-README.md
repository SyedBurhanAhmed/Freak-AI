
# Freak AI - Instructor Setup Guide

This document provides step-by-step instructions to run **Freak AI** — a web-based rule-based chatbot that mimics human brain memory using Neo4j graph database. The project includes both a web dashboard for visualization and chat history, plus a hardware voice interface using ESP32 with environmental sensors.

Freak AI represents a first small step towards AGI (Artificial General Intelligence) by implementing multiple memory systems including social, semantic, PAM, episodic, and sensory memory.

---

## Prerequisites

- **Python 3.13 or above** (Check with `python --version`)
- Neo4j Desktop (download from https://neo4j.com/download/)
- Arduino IDE (for ESP32 hardware interface)
- Hardware components: ESP32 DevKit, PAM8403 speaker module, MAX9814 microphone, DHT11 temperature/humidity sensor

---

## Project Setup Instructions

### 1. Create Python Virtual Environment

```
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate

# On macOS/Linux:
source venv/bin/activate
```

### 2. Extract Project Files

Extract the project zip folder **into the venv directory**:
```
venv/
├── Freak-AI-project/
│   ├── app.py
│   ├── download.py
│   ├── conversation.py
│   ├── requirements.txt
│   ├── ESP_Code/
│   ├── templates/
│   ├── prolog/
│   ├── aiml_files/
│   └── favicon/
```

### 3. Install Dependencies

Navigate to the project folder and install requirements:
```
cd Freak-AI-project
pip install -r requirements.txt
```

### 4. Download NLTK Models

Run the download script to install required NLTK models:
```
python download.py
```

### 5. Setup Neo4j Database

1. **Install Neo4j Desktop** (if not already installed)
   - Download from https://neo4j.com/download/
   - Install and create an account

2. **Create Database**
   - Open Neo4j Desktop
   - Click "New" → "Create Project"
   - Click "Add" → "Local DBMS"
   - Set database name and password
   - Click "Create"

3. **Start Database Instance**
   - Click "Start" on your created database
   - Copy the **Bolt URI** (e.g., `bolt://localhost:7687`)

4. **Configure Database Connection**
   - Open `app.py` file
   - Find the `connect_neo4j()` function
   - Replace the URI with your database URI
   - Update the password to match your Neo4j database password
   - Username remains `neo4j` (unless changed during setup)

### 6. Run Web Application

```
python app.py
```

The application will start at `http://127.0.0.1:5000`

**Usage Instructions:**
1. **Sign Up** first (mandatory before login)
2. **Login** with your credentials
3. **Chat** with the bot on the dashboard
4. **View** real-time memory graphs and chat history visualization

---

## Hardware Voice Interface Setup

### Required Components
- ESP32 DevKit
- PAM8403 Speaker Module + Speaker
- MAX9814 Microphone Module
- DHT11 Temperature & Humidity Sensor

### Arduino IDE Setup

1. **Install Arduino IDE**
   - Download from https://www.arduino.cc/en/software

2. **Add ESP32 Board Support**
   - Go to File → Preferences
   - Add this URL to "Additional Boards Manager URLs":
     ```
     https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
     ```

3. **Install ESP32 Library**
   - Go to Tools → Board → Boards Manager
   - Search for "ESP32" and install

### Hardware Setup

1. **Upload Code**
   - Open the Arduino sketch from `ESP_Code/` folder
   - Select Board: "ESP32 Dev Module"
   - Select appropriate COM port
   - Upload the code

2. **Hardware Connections**
   - Connect PAM8403 speaker module and speaker
   - Connect MAX9814 microphone module
   - Connect DHT11 sensor
   - Power the ESP32 system

3. **Run Hardware Interface**
   ```
   python conversation.py
   ```

**Hardware Usage:**
- Use microphone to login and chat with the bot
- Responses come through the speaker
- Access temperature/humidity sensor data via voice commands

---

## How the System Works

### Memory Architecture
The system implements 5 types of memory:
- **Social Memory**: Relationships and social connections
- **Semantic Memory**: Word meanings and general knowledge
- **PAM Memory**: Personal Associative Memory
- **Episodic Memory**: Conversation sessions and interactions
- **Sensory Memory**: Text-based and sensor-based data

### Data Flow
1. **User Signup**: Creates Neo4j User node and Prolog fact file
2. **User Input**: Processed through AIML and `prompt_check()` function
3. **Fact Processing**: Updates Prolog facts based on user statements
4. **Memory Storage**: Asynchronously saves interactions to Neo4j
5. **Response Generation**: Returns processed response to dashboard/speaker

### Technical Components
- **Flask**: Web framework for dashboard
- **Neo4j**: Graph database for memory storage
- **AIML**: Rule-based chatbot responses
- **Prolog**: Fact-based knowledge representation
- **NLTK**: Natural language processing
- **ESP32**: Hardware interface with sensors

---

## Troubleshooting

**Common Issues:**
- Ensure Neo4j database is running before starting `app.py`
- Check Python version compatibility (3.13+)
- Verify all dependencies are installed in virtual environment
- For ESP32: Check COM port selection and baud rate (115200)

**File Structure:**
```
project/
├── app.py              # Main Flask application
├── download.py         # NLTK model downloader
├── conversation.py     # Hardware interface
├── requirements.txt    # Python dependencies
├── ESP_Code/          # Arduino sketch
├── templates/         # HTML templates
├── prolog/           # Prolog fact files
├── aiml_files/       # AIML chatbot files
└── favicon/          # Web assets
```

---

*Note: Some AIML files are adapted from Pema Grg Easy Chatbot project. The rest of the implementation is original work.*
