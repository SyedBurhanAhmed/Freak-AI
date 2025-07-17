#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Base64.h>
#include <Preferences.h>
#include "DHT.h"

// Hardware Configuration
#define MIC_PIN 34
#define DAC_PIN 25
#define DHTPIN 4
#define DHTTYPE DHT11
#define SAMPLE_RATE 8000
#define RECORD_SECONDS 3
#define TOTAL_SAMPLES (SAMPLE_RATE * RECORD_SECONDS)

const int BASE_DELAY_US = 1000000 / SAMPLE_RATE;
const float PLAYBACK_SPEED_FACTOR = 1.2;
const int PLAYBACK_DELAY_US = BASE_DELAY_US / PLAYBACK_SPEED_FACTOR;
const byte NOISE_THRESHOLD = 10;

// WiFi & Server Configuration
const char* ssid = "Galaxy Note 8";
const char* password = "bidf9564";
const char* serverIP = "192.168.43.237";
const int serverPort = 5001;

// Construct URLs
String serverURL = "http://" + String(serverIP) + ":" + String(serverPort) + "/process_audio_chat_tts";
String downloadTTSURL = "http://" + String(serverIP) + ":" + String(serverPort) + "/download_tts";
String loginURL = "http://" + String(serverIP) + ":" + String(serverPort) + "/esp32_login";
String signupURL = "http://" + String(serverIP) + ":" + String(serverPort) + "/esp32_signup";
String testURL = "http://" + String(serverIP) + ":" + String(serverPort) + "/";

// Global Variables
uint8_t *audioBuffer = NULL;
Preferences preferences;
DHT dht(DHTPIN, DHTTYPE);
WebServer server(80);  // Web server on port 80

// User Session
struct UserSession {
  String email;
  String username;
  String fact_file;
  bool isLoggedIn;
};

UserSession userSession = {"", "", "", false};

// DHT11 Sensor Structure
struct SensoryMemory {
  float temperature;
  float humidity;
  unsigned long timestamp;
  bool valid;
  String sensor_type;
  float comfort_score;
  String recommendations;
  String status;
};

SensoryMemory currentReading = {0, 0, 0, false, "DHT11", 0, "", "disconnected"};
unsigned long lastSensorUpdate = 0;
const unsigned long SENSOR_UPDATE_INTERVAL = 60000; // 1 minute

// =====================================
// DHT11 SENSOR FUNCTIONS
// =====================================
void updateSensoryMemory() {
  float h = dht.readHumidity();
  float t = dht.readTemperature();
  
  if (!isnan(h) && !isnan(t)) {
    currentReading.temperature = t;
    currentReading.humidity = h;
    currentReading.timestamp = millis();
    currentReading.valid = true;
    currentReading.sensor_type = "DHT11";
    currentReading.status = "valid";
    
    // Calculate comfort score (0-100) - Fixed type casting
    float temp_score = max(0.0f, min(100.0f, 100.0f - abs(t - 23.0f) * 10.0f));
    float humidity_score = max(0.0f, min(100.0f, 100.0f - abs(h - 50.0f) * 2.0f));
    currentReading.comfort_score = (temp_score + humidity_score) / 2.0f;
    
    // Generate recommendations
    String recommendations = "";
    if (t > 26.0f) {
      recommendations += "Room temperature is high - consider cooling; ";
    } else if (t < 20.0f) {
      recommendations += "Room temperature is low - consider warming; ";
    }
    
    if (h > 60.0f) {
      recommendations += "Humidity is high - consider dehumidifying; ";
    } else if (h < 40.0f) {
      recommendations += "Humidity is low - consider humidifying; ";
    }
    
    if (recommendations.length() == 0) {
      recommendations = "Environmental conditions are optimal";
    }
    
    currentReading.recommendations = recommendations;
    
    Serial.printf("🌡️ DHT11: %.1f°C, %.1f%% (Comfort: %.0f%%)\n", t, h, currentReading.comfort_score);
  } else {
    currentReading.valid = false;
    currentReading.status = "error";
    Serial.println("❌ DHT11 sensor error");
  }
}


String getSensorDataJSON() {
  StaticJsonDocument<600> doc;
  
  if (currentReading.valid) {
    doc["temperature"] = currentReading.temperature;
    doc["humidity"] = currentReading.humidity;
    doc["timestamp"] = currentReading.timestamp;
    doc["sensor_type"] = currentReading.sensor_type;
    doc["status"] = currentReading.status;
    doc["memory_type"] = "SensoryMemory";
    doc["comfort_score"] = currentReading.comfort_score;
    doc["recommendations"] = currentReading.recommendations;
    doc["esp32_ip"] = WiFi.localIP().toString();
  } else {
    doc["temperature"] = nullptr;
    doc["humidity"] = nullptr;
    doc["timestamp"] = millis();
    doc["sensor_type"] = "DHT11";
    doc["status"] = "error";
    doc["memory_type"] = "SensoryMemory";
    doc["comfort_score"] = 0;
    doc["recommendations"] = "Sensor error - check connections";
    doc["esp32_ip"] = WiFi.localIP().toString();
  }
  
  String jsonString;
  serializeJson(doc, jsonString);
  return jsonString;
}

// =====================================
// WEB SERVER HANDLERS
// =====================================

void handleRoot() {
  String html = "<html><body style='font-family: Arial; text-align: center; padding: 50px;'>";
  html += "<h1>🎙️ ESP32 Voice Assistant + DHT11 Sensor</h1>";
  html += "<div style='background: #f0f0f0; padding: 20px; border-radius: 10px; margin: 20px;'>";
  html += "<h2>📍 Device Information</h2>";
  html += "<p><strong>IP Address:</strong> " + WiFi.localIP().toString() + "</p>";
  html += "<p><strong>MAC Address:</strong> " + WiFi.macAddress() + "</p>";
  html += "<p><strong>Signal Strength:</strong> " + String(WiFi.RSSI()) + " dBm</p>";
  html += "</div>";
  
  html += "<div style='background: #e6f3ff; padding: 20px; border-radius: 10px; margin: 20px;'>";
  html += "<h2>🌡️ Current Sensor Readings</h2>";
  
  if (currentReading.valid) {
    html += "<p><strong>🌡️ Temperature:</strong> " + String(currentReading.temperature) + "°C</p>";
    html += "<p><strong>💧 Humidity:</strong> " + String(currentReading.humidity) + "%</p>";
    html += "<p><strong>😊 Comfort Score:</strong> " + String(currentReading.comfort_score) + "%</p>";
    html += "<p><strong>💡 Recommendations:</strong> " + currentReading.recommendations + "</p>";
    html += "<p><strong>📅 Last Update:</strong> " + String(millis() - currentReading.timestamp) + " ms ago</p>";
  } else {
    html += "<p style='color: red;'>❌ Sensor Error - Check connections</p>";
  }
  html += "</div>";
  
  html += "<div style='background: #f0f8ff; padding: 20px; border-radius: 10px; margin: 20px;'>";
  html += "<h2>👤 User Status</h2>";
  if (userSession.isLoggedIn) {
    html += "<p><strong>Status:</strong> ✅ Logged in</p>";
    html += "<p><strong>Username:</strong> " + userSession.username + "</p>";
    html += "<p><strong>Email:</strong> " + userSession.email + "</p>";
  } else {
    html += "<p><strong>Status:</strong> 🔒 Not logged in</p>";
  }
  html += "</div>";
  
  html += "<div style='margin: 20px;'>";
  html += "<p><a href='/sensor' style='background: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin: 5px;'>Get Sensor Data (JSON)</a></p>";
  html += "<p><a href='/update' style='background: #2196F3; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin: 5px;'>Update Sensor</a></p>";
  html += "</div>";
  
  html += "</body></html>";
  
  server.send(200, "text/html", html);
}

void handleSensor() {
  // Force update sensor reading
  updateSensoryMemory();
  
  String response = getSensorDataJSON();
  server.send(200, "application/json", response);
}

void handleUpdate() {
  updateSensoryMemory();
  String response = "Sensor updated successfully";
  server.send(200, "text/plain", response);
}

void handleNotFound() {
  String message = "File Not Found\n\n";
  message += "URI: ";
  message += server.uri();
  message += "\nMethod: ";
  message += (server.method() == HTTP_GET) ? "GET" : "POST";
  message += "\nArguments: ";
  message += server.args();
  message += "\n";
  
  for (uint8_t i = 0; i < server.args(); i++) {
    message += " " + server.argName(i) + ": " + server.arg(i) + "\n";
  }
  
  server.send(404, "text/plain", message);
}

// =====================================
// AUTHENTICATION FUNCTIONS
// =====================================

void saveUserSession() {
  preferences.begin("user_session", false);
  preferences.putString("email", userSession.email);
  preferences.putString("username", userSession.username);
  preferences.putString("fact_file", userSession.fact_file);
  preferences.putBool("isLoggedIn", userSession.isLoggedIn);
  preferences.end();
}

void loadUserSession() {
  preferences.begin("user_session", true);
  userSession.email = preferences.getString("email", "");
  userSession.username = preferences.getString("username", "");
  userSession.fact_file = preferences.getString("fact_file", "");
  userSession.isLoggedIn = preferences.getBool("isLoggedIn", false);
  preferences.end();
  
  if (userSession.isLoggedIn) {
    Serial.println("🔐 Loaded session for: " + userSession.username);
  }
}

void clearUserSession() {
  userSession = {"", "", "", false};
  preferences.begin("user_session", false);
  preferences.clear();
  preferences.end();
  Serial.println("🔒 Session cleared");
}

bool testNetworkConnection() {
  Serial.println("🔍 Testing network connection...");
  
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("❌ WiFi not connected");
    return false;
  }
  
  Serial.println("✅ WiFi connected");
  Serial.print("📍 Device IP: ");
  Serial.println(WiFi.localIP());
  
  HTTPClient http;
  http.begin(testURL);
  http.setTimeout(10000);
  
  Serial.println("🔍 Testing server connection to: " + testURL);
  
  int httpResponseCode = http.GET();
  
  if (httpResponseCode > 0) {
    Serial.printf("✅ Server responded with code: %d\n", httpResponseCode);
    http.end();
    return true;
  } else {
    Serial.printf("❌ Server connection failed: %d\n", httpResponseCode);
    http.end();
    return false;
  }
}

bool performLogin() {
  if (!testNetworkConnection()) {
    Serial.println("❌ Cannot connect to server");
    return false;
  }
  
  String email = "";
  String password = "";
  
  Serial.println("\n=== 🔐 ESP32 LOGIN ===");
  Serial.println("Enter your email:");
  
  while (email.length() == 0) {
    if (Serial.available()) {
      email = Serial.readString();
      email.trim();
    }
    delay(100);
  }
  
  Serial.println("Email: " + email);
  Serial.println("Enter your password:");
  
  while (password.length() == 0) {
    if (Serial.available()) {
      password = Serial.readString();
      password.trim();
    }
    delay(100);
  }
  
  HTTPClient http;
  http.begin(loginURL);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(20000);
  
  StaticJsonDocument<200> loginDoc;
  loginDoc["email"] = email;
  loginDoc["password"] = password;
  loginDoc["source"] = "esp32";
  
  String loginData;
  serializeJson(loginDoc, loginData);
  
  Serial.println("📡 Sending login request...");
  int httpResponseCode = http.POST(loginData);
  
  if (httpResponseCode > 0) {
    String response = http.getString();
    Serial.println("📄 Server Response: " + response);
    
    DynamicJsonDocument doc(1024);
    DeserializationError error = deserializeJson(doc, response);
    
    if (!error && doc["success"]) {
      userSession.email = doc["email"].as<String>();
      userSession.username = doc["username"].as<String>();
      userSession.fact_file = doc["fact_file"].as<String>();
      userSession.isLoggedIn = true;
      
      saveUserSession();
      
      Serial.println("✅ Login successful!");
      Serial.println("👤 Welcome: " + userSession.username);
      
      http.end();
      return true;
    } else {
      Serial.println("❌ Login failed!");
      if (doc.containsKey("error")) {
        Serial.println("   Reason: " + doc["error"].as<String>());
      }
    }
  } else {
    Serial.printf("❌ HTTP Request Failed: %d\n", httpResponseCode);
  }
  
  http.end();
  return false;
}

bool performSignup() {
  if (!testNetworkConnection()) {
    Serial.println("❌ Cannot connect to server for signup");
    return false;
  }
  
  String name = "";
  String email = "";
  String password = "";
  String confirmPassword = "";
  
  Serial.println("\n=== 📝 ESP32 SIGNUP ===");
  Serial.println("Enter your name:");
  
  while (name.length() == 0) {
    if (Serial.available()) {
      name = Serial.readString();
      name.trim();
    }
    delay(100);
  }
  
  Serial.println("Name: " + name);
  Serial.println("Enter your email:");
  
  while (email.length() == 0) {
    if (Serial.available()) {
      email = Serial.readString();
      email.trim();
    }
    delay(100);
  }
  
  Serial.println("Email: " + email);
  Serial.println("Enter your password:");
  
  while (password.length() == 0) {
    if (Serial.available()) {
      password = Serial.readString();
      password.trim();
    }
    delay(100);
  }
  
  Serial.println("Confirm your password:");
  
  while (confirmPassword.length() == 0) {
    if (Serial.available()) {
      confirmPassword = Serial.readString();
      confirmPassword.trim();
    }
    delay(100);
  }
  
  if (password != confirmPassword) {
    Serial.println("❌ Passwords don't match!");
    return false;
  }
  
  HTTPClient http;
  http.begin(signupURL);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(20000);
  
  StaticJsonDocument<300> signupDoc;
  signupDoc["name"] = name;
  signupDoc["email"] = email;
  signupDoc["password"] = password;
  signupDoc["confirm_password"] = confirmPassword;
  signupDoc["source"] = "esp32";
  
  String signupData;
  serializeJson(signupDoc, signupData);
  
  Serial.println("📡 Sending signup request...");
  int httpResponseCode = http.POST(signupData);
  
  if (httpResponseCode > 0) {
    String response = http.getString();
    Serial.println("📄 Signup response: " + response);
    
    DynamicJsonDocument doc(1024);
    DeserializationError error = deserializeJson(doc, response);
    
    if (!error && doc["success"]) {
      Serial.println("✅ Signup successful!");
      Serial.println("📧 Account created for: " + email);
      
      http.end();
      return true;
    } else {
      Serial.println("❌ Signup failed: " + doc["error"].as<String>());
    }
  } else {
    Serial.printf("❌ HTTP error: %d\n", httpResponseCode);
  }
  
  http.end();
  return false;
}

// =====================================
// AUDIO FUNCTIONS
// =====================================

void recordAudio(uint8_t* buffer, uint32_t numSamples) {
  Serial.println("🎤 Recording audio...");
  for (uint32_t i = 0; i < numSamples; i++) {
    int micValue = analogRead(MIC_PIN);
    uint8_t audioValue = micValue >> 4;
    int deviation = 128 - audioValue;
    if (abs(deviation) < NOISE_THRESHOLD) {
      audioValue = 128;
    }
    buffer[i] = audioValue;
    delayMicroseconds(BASE_DELAY_US);
  }
  Serial.println("✅ Recording complete.");
}

bool sendAudioToServer() {
  if (!userSession.isLoggedIn) {
    Serial.println("❌ Please login first (press 'l' to login)");
    return false;
  }
  
  // Update sensor data before sending
  updateSensoryMemory();
  
  HTTPClient http;
  http.begin(serverURL);
  http.addHeader("Content-Type", "application/octet-stream");
  http.addHeader("User-Email", userSession.email);
  http.addHeader("User-Fact-File", userSession.fact_file);
  http.addHeader("User-Name", userSession.username);
  http.addHeader("Sensor-Data", getSensorDataJSON());
  
  http.setTimeout(30000);
  
  Serial.println("📡 Sending audio + sensor data as " + userSession.username + "...");
  int httpResponseCode = http.POST(audioBuffer, TOTAL_SAMPLES);
  
  if (httpResponseCode == 200) {
    String response = http.getString();
    Serial.println("🌐 Server response received");
    
    DynamicJsonDocument doc(2048);
    DeserializationError error = deserializeJson(doc, response);
    
    if (!error) {
      String recognizedText = doc["recognized_text"].as<String>();
      String chatbotResponse = doc["chatbot_response"].as<String>();
      
      Serial.println("=== 🤖 SPEECH RECOGNITION RESULT ===");
      Serial.println("👤 " + userSession.username + ": " + recognizedText);
      Serial.println("🤖 Chatbot: " + chatbotResponse);
      Serial.println("==================================");
      
      delay(2000);
      downloadAndPlayTTS();
      
    } else {
      Serial.println("❌ JSON parsing error: " + String(error.c_str()));
    }
    
    http.end();
    return true;
  } else {
    Serial.printf("❌ HTTP error: %d\n", httpResponseCode);
    http.end();
    return false;
  }
}

void downloadAndPlayTTS() {
  int maxRetries = 3;
  
  for (int attempt = 1; attempt <= maxRetries; attempt++) {
    Serial.printf("🔊 Downloading TTS audio (attempt %d/%d)...\n", attempt, maxRetries);
    
    HTTPClient http;
    http.begin(downloadTTSURL);
    http.setTimeout(20000);
    
    int httpResponseCode = http.GET();
    
    if (httpResponseCode == 200) {
      WiFiClient* stream = http.getStreamPtr();
      
      if (stream->available()) {
        Serial.println("🎵 Playing TTS audio...");
        
        // Skip WAV header
        const int WAV_HEADER_SIZE = 44;
        for (int i = 0; i < WAV_HEADER_SIZE; i++) {
          int timeout = 0;
          while (!stream->available() && timeout < 1000) {
            delay(10);
            timeout++;
          }
          if (stream->available()) {
            stream->read();
          }
        }
        
        // Play audio
        while (stream->available()) {
          uint8_t sample = stream->read();
          dacWrite(DAC_PIN, sample);
          delayMicroseconds(PLAYBACK_DELAY_US);
        }
        
        Serial.println("🎵 TTS playback complete.");
        http.end();
        return;
      }
    } else {
      Serial.printf("❌ TTS download failed, HTTP code: %d\n", httpResponseCode);
    }
    
    http.end();
    
    if (attempt < maxRetries) {
      delay(2000);
    }
  }
  
  Serial.println("❌ TTS download failed after all retries");
}

// =====================================
// SETUP AND LOOP
// =====================================

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  
  // Initialize DHT sensor
  dht.begin();
  
  // Initialize preferences
  preferences.begin("esp32_auth", false);
  
  // Load saved session
  loadUserSession();
  
  // WiFi connection
  WiFi.begin(ssid, password);
  Serial.print("🔗 Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.print(".");
  }
  Serial.println();
  
  // Print IP address
  Serial.print("✅ Connected to WiFi. Device IP: ");
  Serial.println(WiFi.localIP());
  
  // Initialize sensor
  updateSensoryMemory();
  
  // Start web server
  server.on("/", handleRoot);
  server.on("/sensor", handleSensor);
  server.on("/update", handleUpdate);
  server.onNotFound(handleNotFound);
  server.begin();
  
  Serial.println("🌐 Web server started on port 80");
  Serial.println("📡 Access sensor at: http://" + WiFi.localIP().toString() + "/sensor");
  Serial.println("🏠 Web interface at: http://" + WiFi.localIP().toString());

  // Audio buffer allocation
  audioBuffer = (uint8_t*) malloc(TOTAL_SAMPLES);
  if (!audioBuffer) {
    Serial.println("❌ Failed to allocate audio buffer");
    while (true) delay(1000);
  }
  
  Serial.println("\n=== 🎙️ COMPLETE VOICE ASSISTANT + SENSOR ===");
  Serial.println("Server: " + String(serverIP) + ":" + String(serverPort));
  Serial.print("ESP32 IP: ");
  Serial.println(WiFi.localIP());
  
  if (userSession.isLoggedIn) {
    Serial.println("👤 Logged in as: " + userSession.username);
  } else {
    Serial.println("🔒 Not logged in");
  }
  
  Serial.println("\nCommands:");
  Serial.println("  [SPACE] - Voice recording (requires login)");
  Serial.println("  'l' - Login");
  Serial.println("  'r' - Register/Signup");
  Serial.println("  'o' - Logout");
  Serial.println("  's' - Show sensor status");
  Serial.println("  'u' - Update sensor");
  Serial.println("  'i' - Show user info");
  Serial.println("  'c' - Check connection");
  Serial.println("================================================\n");
}

void loop() {
  // Handle web server requests
  server.handleClient();
  
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("📡 WiFi disconnected. Reconnecting...");
    WiFi.reconnect();
    delay(1000);
    return;
  }

  // Auto-update sensor
  if (millis() - lastSensorUpdate >= SENSOR_UPDATE_INTERVAL) {
    updateSensoryMemory();
    lastSensorUpdate = millis();
  }

  // Handle commands
  if (Serial.available()) {
    char inputChar = Serial.read();
    while (Serial.available()) Serial.read();

    switch (inputChar) {
      case ' ':
        if (userSession.isLoggedIn) {
          Serial.println("🎤 Voice recording for " + userSession.username);
          recordAudio(audioBuffer, TOTAL_SAMPLES);
          
          if (sendAudioToServer()) {
            Serial.println("✅ Voice processing completed");
          } else {
            Serial.println("❌ Voice processing failed");
          }
        } else {
          Serial.println("🔒 Please login first (press 'l')");
        }
        break;
        
      case 'l':
        if (performLogin()) {
          Serial.println("🎉 You can now use voice commands!");
        }
        break;
        
      case 'r':
        if (performSignup()) {
          Serial.println("✅ Account created! Now login with 'l'");
        }
        break;
        
      case 'o':
        clearUserSession();
        break;
        
      case 's':
        Serial.println("\n=== 🌡️ DHT11 SENSOR STATUS ===");
        if (currentReading.valid) {
          Serial.printf("🌡️ Temperature: %.1f°C\n", currentReading.temperature);
          Serial.printf("💧 Humidity: %.1f%%\n", currentReading.humidity);
          Serial.printf("😊 Comfort Score: %.0f%%\n", currentReading.comfort_score);
          Serial.printf("💡 Recommendations: %s\n", currentReading.recommendations.c_str());
          Serial.printf("📅 Last Update: %lu ms ago\n", (millis() - currentReading.timestamp));
        } else {
          Serial.println("❌ Sensor Status: ERROR");
        }
        Serial.println("============================\n");
        break;
        
      case 'u':
        updateSensoryMemory();
        break;
        
      case 'i':
        Serial.println("\n=== 👤 USER INFO ===");
        if (userSession.isLoggedIn) {
          Serial.println("📧 Email: " + userSession.email);
          Serial.println("👤 Username: " + userSession.username);
          Serial.println("📁 Fact file: " + userSession.fact_file);
        } else {
          Serial.println("🔒 Not logged in");
        }
        Serial.println("🌐 Server: " + String(serverIP) + ":" + String(serverPort));
        Serial.print("📍 ESP32 IP: ");
        Serial.println(WiFi.localIP());
        Serial.print("📶 WiFi RSSI: ");
        Serial.print(WiFi.RSSI());
        Serial.println(" dBm");
        Serial.println("==================\n");
        break;
        
      case 'c':
        testNetworkConnection();
        break;
        
      default:
        Serial.println("❓ Unknown command. Available commands:");
        Serial.println("  [SPACE] - Voice recording");
        Serial.println("  'l' - Login");
        Serial.println("  'r' - Register");
        Serial.println("  'o' - Logout");
        Serial.println("  's' - Sensor status");
        Serial.println("  'u' - Update sensor");
        Serial.println("  'i' - User info");
        Serial.println("  'c' - Check connection");
        break;
    }
  }
  
  delay(100);
}
