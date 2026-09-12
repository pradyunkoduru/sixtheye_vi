#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include "driver/i2s.h"

// --- WI-FI & SERVER CONFIGURATION ---

const char *ssid = "APMV";
const char *password = "vdnu1678";
// Replace with your Laptop's Local IP Address
const char* serverUrl = "http://192.168.1.164:5000/process-image"; 
//http://192.168.1.184/

// --- PIN DEFINITIONS ---
#define BUTTON_PIN        1  // D0 on Grove Shield

// MAX98357A I2S Amplifier Pins
#define I2S_LRC           2   // D1
#define I2S_BCLK          3   // D2
#define I2S_DIN           4   // D3
#define I2S_NUM           I2S_NUM_0

// XIAO ESP32-S3 Sense Camera Pinout
#define PWDN_GPIO_NUM     -1
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM     10
#define SIOD_GPIO_NUM     40
#define SIOC_GPIO_NUM     39
#define Y9_GPIO_NUM       48
#define Y8_GPIO_NUM       11
#define Y7_GPIO_NUM       12
#define Y6_GPIO_NUM       14
#define Y5_GPIO_NUM       16
#define Y4_GPIO_NUM       18
#define Y3_GPIO_NUM       17
#define Y2_GPIO_NUM       15
#define VSYNC_GPIO_NUM    38
#define HREF_GPIO_NUM     47
#define PCLK_GPIO_NUM     13

void setupI2S() {
  i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX),
    .sample_rate = 16000,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 8,
    .dma_buf_len = 64,
    .use_apll = false
  };

  i2s_pin_config_t pin_config = {
    .bck_io_num = I2S_BCLK,
    .ws_io_num = I2S_LRC,
    .data_out_num = I2S_DIN,
    .data_in_num = I2S_PIN_NO_CHANGE
  };

  i2s_driver_install(I2S_NUM, &i2s_config, 0, NULL);
  i2s_set_pin(I2S_NUM, &pin_config);
}

void setupCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.frame_size = FRAMESIZE_UXGA; // Max res for 180-deg detail
  config.pixel_format = PIXFORMAT_JPEG;
  config.grab_mode = CAMERA_GRAB_LATEST;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.jpeg_quality = 10;
  config.fb_count = 1;

  if (esp_camera_init(&config) != ESP_OK) {
    Serial.println("Camera Init Failed!");
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(BUTTON_PIN, INPUT);

  setupCamera();
  setupI2S();

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi Connected!");
}

void loop() {
  // Check if button is pressed (LOW when pressed)
  //Serial.println(digitalRead(BUTTON_PIN));
  if (digitalRead(BUTTON_PIN) == HIGH) {
    Serial.println("Button Pressed! Capturing Frame...");
    delay(300); // Debounce

    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("Capture Failed!");
      while (digitalRead(BUTTON_PIN) == HIGH) { delay(10); }
      return;
    }

    Serial.println("Capture Success!");

    HTTPClient http;
    http.begin(serverUrl);
    http.addHeader("Content-Type", "image/jpeg");
    http.addHeader("Connection", "close");

    http.setTimeout(100000);

    Serial.println("Sending image to Python server...");
    int httpResponseCode = http.POST(fb->buf, fb->len);

    if (httpResponseCode == 200) {
      Serial.println("Image processed! Playing audio response...");
      WiFiClient* stream = http.getStreamPtr();
      Serial.println("Audio 1");


      
      // Skip the 44-byte WAV Header to get straight to RAW PCM data
      uint8_t header[44];
      stream->readBytes(header, 44);

      Serial.println("Audio 2");


      // Stream the raw audio data straight to the I2S speaker
      uint8_t buffer[512];
      size_t bytesWritten;

      while (http.connected() && (stream->available() || stream->connected())) {
        Serial.println("Audio 3");
        size_t size = stream->readBytes(buffer, sizeof(buffer));
        Serial.println(size);

        static bool firstChunk = true;
        if (firstChunk) {
           Serial.printf("First 4 bytes (HEX): %02X %02X %02X %02X\n", buffer[0], buffer[1], buffer[2], buffer[3]);
           //Serial.printf("Total File Size: %d\n", len); // Let's also check if it knows the file size
           Serial.printf("First 4 bytes: %c %c %c %c\n", buffer[0], buffer[1], buffer[2], buffer[3]);
           firstChunk = false;
        }

        if (size > 0) {
          Serial.println("Audio 5");

          i2s_write(I2S_NUM, buffer, size, &bytesWritten, portMAX_DELAY);
        }
      }
    } else {
      Serial.printf("HTTP POST failed, error: %s\n", http.errorToString(httpResponseCode).c_str());
      //Serial.printf("Server error: %d\n", httpResponseCode);
    }

    http.end();
    esp_camera_fb_return(fb); // Clear RAM

    // Wait until button is released before allowing next capture
    while (digitalRead(BUTTON_PIN) == HIGH) { delay(10); }
  }
}