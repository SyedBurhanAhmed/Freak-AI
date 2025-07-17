
# Freak AI 🧠🤖  
*A memory-centric, rule-based conversational agent with Neo4j graph storage, real-time dashboards and an optional ESP32 voice/sensor interface.*

[![Python](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/)  
[![Flask](https://img.shields.io/badge/flask-web%20app-green.svg)](https://flask.palletsprojects.com/)  
[![Neo4j](https://img.shields.io/badge/neo4j-graph%20dbms-red.svg)](https://neo4j.com/)  
[![ESP32](https://img.shields.io/badge/esp32-supported-orange.svg)](https://github.com/espressif/arduino-esp32)  

---

## ✨ Project Vision
Freak AI is our **first small step toward AGI**.  
It models five human-inspired memory systems—**social, semantic, PAM, episodic and sensory**—inside a Neo4j graph.  
You can:

* Chat through a **web dashboard** and watch memories grow in real-time graphs.
* Talk to an **Alexa-style ESP32 device** that speaks back and records sensor data (DHT11 temperature/humidity).

---

## 📦 Repository Layout
```
Freak-AI/
├── app.py             # Flask web backend
├── download.py        # One-shot NLTK model downloader
├── conversation.py    # Voice / hardware interface
├── requirements.txt   # Python deps
├── ESP_Code/          # Arduino sketch for ESP32
├── templates/         # HTML (Jinja2) files
├── aiml_files/        # AIML knowledge base (partially from Pema Grg Easy Chatbot)
├── prolog/            # Per-user Prolog fact files
└── favicon/           # Static assets
```

---

## 🚀 Quick Start (Web Only)

### 1. Clone & enter repo
```
git clone https://github.com//Freak-AI.git
cd Freak-AI
```

### 2. Python 3.13+ virtual environment
```
python -m venv venv
# Win
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies
```
pip install -r requirements.txt
python download.py          # grabs NLTK corpora
```

### 4. Neo4j Desktop
1. Install Neo4j Desktop ⟶ create a **Local DBMS**  
2. Start it and copy its **Bolt URI** (e.g. `bolt://localhost:7687`)  
3. Open `app.py` → `connect_neo4j()` → paste URI & your password  
   (username default = `neo4j`)

### 5. Launch!
```
python app.py
```
Visit `http://127.0.0.1:5000` → **Sign Up** → **Log In** → chat & explore graphs.

---

## 🔊 Hardware Voice Interface (Optional)

| Component | Qty |
|-----------|-----|
| ESP32 DevKit | 1 |
| PAM8403 speaker amp + speaker | 1 |
| MAX9814 mic module | 1 |
| DHT11 temp / humidity sensor | 1 |

1. Install **Arduino IDE** and **ESP32 core**:  
   Boards Manager URL  
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
2. Open `ESP_Code/voice_interface.ino`  
3. Tools → Board: “ESP32 Dev Module” → select COM port → **Upload**  
4. Wire speaker, mic, DHT11 → power up  
5. Back in your venv:
   ```
   python conversation.py
   ```
   Speak to log in → issue commands (“temperature?”, “tell me a joke” …) → hear responses.

---

## 🧠 How It Works

1. **AIML** produces predicates from each utterance.  
2. `prompt_check()` updates Prolog facts, queries definitions, handles sensor predicates, etc.  
3. `async_create_interaction()` stores *sensory / semantic / PAM / episodic* memories plus user ↔ agent links in **Neo4j**.  
4. Dashboard (D3.js) streams updated memory graphs.

---

## 🤝 Contributing

1. Fork → create feature branch → PR  
2. Follow PEP8; run `black .` before committing.  
3. Large changes? Open an issue first.

---

## 📜 License

Freak AI is released under the **MIT License**.  
Some AIML snippets are © Pema Grg Easy Chatbot (MIT-compatible).

---

## ✍️ Authors & Acknowledgments

- Main author: *Your Name*  
- Hardware inspiration: ESP32 & Arduino communities  
- Special thanks: Neo4j & AIML open-source ecosystems

---

> **Star ⭐ this repo** if you like projects that push classic rule-based AI toward richer memory models!
