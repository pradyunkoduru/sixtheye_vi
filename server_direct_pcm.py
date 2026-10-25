import os
import asyncio
from flask import Flask, request, send_file
from google import genai
from google.genai import types
from PIL import Image
import io
import pyttsx3
import edge_tts
from pydub import AudioSegment
from flask import Response 
import wave


app = Flask(__name__)

# Initialize Gemini Client (Ensure GEMINI_API_KEY environment variable is set)
client = genai.Client(api_key="")

async def generate_speech(text, output_mp3):
    """Converts text to MP3 using Edge-TTS."""
    communicate = edge_tts.Communicate(text, "en-US-AvaNeural")
    await communicate.save(output_mp3)

def convert_mp3_to_wav(mp3_path, wav_path):
    """Converts MP3 to 16kHz, 16-bit Mono WAV format required for ESP32 I2S."""
    sound = AudioSegment.from_mp3(mp3_path)
    sound = sound.set_frame_rate(16000).set_channels(1).set_sample_width(2)
    sound.export(wav_path, format="wav")


def text_to_wav_local(text: str, output_wav_filename: str = "response.wav"):
    """
    Generates a true 16-bit PCM WAV file natively on disk using pyttsx3.
    """
    engine = pyttsx3.init()
    engine.setProperty('rate', 150)  # Speech rate
    
    # Save directly to disk
    engine.save_to_file(text, output_wav_filename)
    engine.runAndWait()

    print(f"Valid WAV file saved to disk: {os.path.abspath(output_wav_filename)}")


@app.route('/ping', methods=['GET'])
def ping():
    return "Server is reachable!", 200


@app.route('/process-image', methods=['POST'])
def process_image():
    print("Received image request from ESP32...\n")
    
    # 1. Read Image
    image_bytes = request.data
    image = Image.open(io.BytesIO(image_bytes))
    
    # 2. Query Gemini Vision API
    prompt = "Describe what you see in the picture concisely in under 20 words for an audio message."

    print("Calling LLM model...\n")

    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=[image, prompt]
    )
    
    ai_text = response.text
    print(f"AI Response: {ai_text}")

    # 3. Text-to-Speech Generation
    #mp3_file = "response.mp3"
    wav_file = "response.wav"
    
    #asyncio.run(generate_speech(ai_text, mp3_file))
    #convert_mp3_to_wav(mp3_file, wav_file)
    text_to_wav_local(ai_text, wav_file)

    with wave.open(wav_file, 'rb') as wf:
        raw_pcm_data = wf.readframes(wf.getnframes())

    # Send the raw bytes back to the ESP32
    return Response(raw_pcm_data, mimetype="application/octet-stream",
        headers={
        "Content-Length": str(len(raw_pcm_data)),
        "Connection": "close"
    })

    # 4. Return the WAV file back to ESP32
    #return send_file("response.wav", mimetype="audio/wav", as_attachment=False)

if __name__ == '__main__':
    # Listen on all interfaces on port 5000
    app.run(host='0.0.0.0', port=5000, debug=True)