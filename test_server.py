import os
import asyncio
import wave
from flask import Flask, request, send_file
from google import genai
from google.genai import types
from PIL import Image
import io
import edge_tts
import pyttsx3
from pydub import AudioSegment


# Initialize Gemini Client (Ensure GEMINI_API_KEY environment variable is set)
client = genai.Client(api_key="<key>")


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

async def text_to_wav_direct(text: str, output_wav_filename: str = "response.wav") -> io.BytesIO:
    """
    Uses edge-tts to generate neural speech and writes raw PCM bytes directly 
    into a 24kHz Mono WAV file (both on disk and as an in-memory stream).
    """
    import edge_tts

    # Select voice: "en-US-AvaNeural" or "en-IN-NeerjaNeural"
    communicate = edge_tts.Communicate(text, "en-US-AvaNeural")
    
    pcm_bytes = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            pcm_bytes.extend(chunk["data"])

    # 1. Save directly to disk in current directory
    with wave.open(output_wav_filename, 'wb') as wf:
        wf.setnchannels(1)       # Mono
        wf.setsampwidth(2)      # 16-bit
        wf.setframerate(24000)  # 24kHz sample rate (matches ESP32 setup)
        wf.writeframes(pcm_bytes)

    print(f"Direct WAV file saved to disk: {os.path.abspath(output_wav_filename)}")

    # 2. Return as an in-memory stream for HTTP transmission
    wav_io = io.BytesIO()
    with wave.open(wav_io, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm_bytes)
    wav_io.seek(0)
    
    return wav_io


def pcm_to_wav_stream(pcm_bytes: bytes, sample_rate: int = 24000, channels: int = 1, sample_width: int = 2, save_filename: str = "response.wav") -> io.BytesIO:
    """
    Wraps raw 16-bit PCM audio bytes directly into an in-memory WAV file stream
    AND saves a copy of the WAV file to the current working directory.
    """
    # 1. Save the file to the current directory
    with wave.open(save_filename, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    
    print(f"Saved audio file to current directory: {os.path.abspath(save_filename)}")

    # 2. Prepare an in-memory stream to send back over HTTP to the ESP32
    wav_io = io.BytesIO()
    with wave.open(wav_io, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    wav_io.seek(0)
    
    return wav_io


async def generate_speech(text, output_mp3):
    """Converts text to MP3 using Edge-TTS."""
    communicate = edge_tts.Communicate(text, "en-US-AvaNeural")
    await communicate.save(output_mp3)

def convert_mp3_to_wav(mp3_path, wav_path):
    """Converts MP3 to 16kHz, 16-bit Mono WAV format required for ESP32 I2S."""
    sound = AudioSegment.from_mp3(mp3_path)
    sound = sound.set_frame_rate(16000).set_channels(1).set_sample_width(2)
    sound.export(wav_path, format="wav")

def process_image(image_path):
   
    # 1. Read Image
    #image_bytes = request.data
    #image = Image.open(io.BytesIO(image_bytes))
    
    image = Image.open(image_path)
    
    # 2. Query Gemini Vision API
    prompt = \
        "Attached is an image. This is for helping vision-impaired individuals. Study the image and tell me what you see." \
        " This is the order of importance, in decreasing priority, that I want you to focus on. " \
        " Starting at the top of the list, look for the items described. Only describe the top three items you find in the image. " \
        " For each item you describe, describe the object, tell me where it is located in relation to the camera, and tell me how far away it is. " \
        " For each object, only print one concise sentence. Brevity is very important for this application. For distances, use meters. " \
        " Do not print any other text, such as a description of the list. Do not number the items in the list." \
        "1. Stairs going up or down 2. Elevator doors 3. Other doors 4. Any hallways 5. Sidewalk 6. Any other pathways 7. A roadway " \
        "8. Any other significant object" 


    print(prompt)

    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=[image, prompt]
    )
    
    ai_text = response.text
    print(f"AI Response: {ai_text}")

    # 3. Text-to-Speech Generation
    mp3_file = "response.mp3"
    wav_file = "response.wav"
    
    # 2. Convert text directly to WAV via edge-tts
    print("Converting text directly to WAV using edge-tts...")
    text_to_wav_local(ai_text, wav_file)
    #wav_stream = asyncio.run(text_to_wav_direct(ai_text, "response.wav"))
    #asyncio.run(generate_speech(ai_text, mp3_file))
    #convert_mp3_to_wav(mp3_file, wav_file)

    # 4. Return the WAV file back to ESP32
    return wav_file


def process_image1(image_path):
    print("Received image request from ESP32...")
    
    # 1. Read incoming JPEG from ESP32
    #image_bytes = request.data
    #image = Image.open(io.BytesIO(image_bytes))
    Image.open(image_path)
    
    prompt = \
    "Describe the image given for helping vision-impaired individuals. Study the image and tell me what you see." \
    " Only describe the top three items you find in the image. " \
    " For each item you describe, describe the object, tell me where it is located in relation to the camera, and tell me how far away it is. " \
    " For each object, only print one concise sentence. Brevity is very important for this application. For distances, use meters. " \
    " Do not print any other text, such as a description of the list. Do not number the items in the list." \
    " See if you find any of the below listed ones in the image and focus on them. Consider the order to be in decreasing priority. " \
    "1. Stairs going up or down 2. Elevator doors 3. Other doors 4. Any hallways 5. Sidewalk 6. Any other pathways 7. A roadway " \
    "8. Any other significant object" 
    " Do not list any object or thing that is not in the image"

    print(prompt)
    
    try:
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=[image, prompt],
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"], # Request audio response directly from model
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name='Kore' # Voice choices: 'Puck', 'Charon', 'Kore', 'Fenrir', 'Aoede'
                        )
                    )
                )
            )
        )

        # 3. Extract raw PCM audio bytes returned directly by the LLM
        print(response)
        audio_part = response.candidates[0].content.parts[0].inline_data    
        raw_pcm_bytes = audio_part.data
        
        print("Successfully generated direct audio from Gemini LLM!")

        # 4. Convert PCM bytes directly into an in-memory WAV file
        wav_file_stream = pcm_to_wav_bytes(raw_pcm_bytes, sample_rate=24000)

        # 5. Return the WAV audio directly to ESP32
        return send_file(
            wav_file_stream,
            mimetype="audio/wav",
            as_attachment=False,
            download_name="response.wav"
        )

    except Exception as e:
        print(f"Error generating audio: {e}")
        return "Failed to process image", 500


if __name__ == '__main__':
    # Listen on all interfaces on port 5000
    #image = "C:\\Users\\vimal\\OneDrive\\Desktop\\PradyunRobotics\\PROJECTS\\Open Eye\\final_code\\test_pictures\\test1.jpg"
    image = "C:/Users/vimal/OneDrive/Desktop/PradyunRobotics/PROJECTS/Open Eye/final_code/test_pictures/test1.jpg"
    #process_image1(image)
    process_image(image)
    