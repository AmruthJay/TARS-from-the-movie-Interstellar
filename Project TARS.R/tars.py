import os
import re
import subprocess
import sounddevice as sd
from scipy.io.wavfile import read
import speech_recognition as sr
from TTS.api import TTS
from ollama import chat

# Initialize the TTS engine (multi-speaker model)
tts = TTS(model_name="tts_models/en/vctk/vits")

# Global personality parameters stored as fractions (0 to 1)
honesty_level = 0.8  # Default: 80%
humor_level = 0.6    # Default: 60%

# Global variable to remember the last parameter queried ("honesty" or "humor")
pending_param = None

def listen():
    """Capture user speech and return recognized text in lowercase."""
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("Listening...")
        audio = recognizer.listen(source)
    try:
        text = recognizer.recognize_google(audio)
        print(f"User said: {text}")
        return text.lower()
    except sr.UnknownValueError:
        print("Sorry, I did not understand that.")
    except sr.RequestError as e:
        print(f"Request error: {e}")
    return ""

def speak(text):
    """Convert text to speech (using a male speaker) and play it."""
    print(f"TARS: {text}")
    audio_output = "response.wav"
    try:
        tts.tts_to_file(text=text, file_path=audio_output, speaker="p267")
        rate, data = read(audio_output)
        sd.play(data, rate)
        sd.wait()
    except Exception as e:
        print(f"Error during TTS synthesis/playback: {e}")

def adjust_personality(user_input):
    """
    Adjust personality parameters if the user commands:
      - "set [your] honesty level to X" or "adjust [your] honesty level to X"
      - "set [your] humor level to Y" or "adjust [your] humor level to Y"
    Also supports commands like "set it to X" if a parameter was recently queried.
    Accepts numbers either as fractions (0.7) or percentages (70 or 70%).
    """
    global honesty_level, humor_level, pending_param

    # Pattern when the parameter is explicitly stated; allow an optional "your"
    pattern_full = r"(set|adjust)\s+(?:your\s+)?(honesty|humor)(\s+level)?\s+to\s+(\d+(?:\.\d+)?)(\s*%| percent)?"
    match = re.search(pattern_full, user_input)
    if match:
        param = match.group(2)
        value_str = match.group(4)
        percent_indicator = match.group(5)
        try:
            value = float(value_str)
            if percent_indicator or value > 1:
                value = value / 100.0  # Convert percentage to fraction.
            value = max(0.0, min(value, 1.0))
            if param == "honesty":
                honesty_level = value
                pending_param = None  # Clear pending since it's explicit.
                return f"Adjusted my honesty level to {value*100:.0f} percent."
            elif param == "humor":
                humor_level = value
                pending_param = None
                return f"Adjusted my humor level to {value*100:.0f} percent."
        except Exception as e:
            print(f"Error adjusting personality: {e}")
    
    # Pattern for "set it to X" using the pending parameter.
    pattern_it = r"(set|adjust)\s+it\s+to\s+(\d+(?:\.\d+)?)(\s*%| percent)?"
    match2 = re.search(pattern_it, user_input)
    if match2 and pending_param:
        value_str = match2.group(2)
        percent_indicator = match2.group(3)
        try:
            value = float(value_str)
            if percent_indicator or value > 1:
                value = value / 100.0
            value = max(0.0, min(value, 1.0))
            if pending_param == "honesty":
                honesty_level = value
                result = f"Adjusted my honesty level to {value*100:.0f} percent."
            elif pending_param == "humor":
                humor_level = value
                result = f"Adjusted my humor level to {value*100:.0f} percent."
            pending_param = None  # Clear after use.
            return result
        except Exception as e:
            print(f"Error adjusting personality with pending param: {e}")
    return None

def generate_llm_response(user_input):
    """
    Use the language model to generate a response as TARS.
    The system prompt instructs the model to think like TARS using the current personality parameters,
    and to remain within the context of the Interstellar mission.
    Provide your answer as a single concise sentence without extraneous commentary.
    """
    system_prompt = (
        f"You are TARS, the advanced AI from Interstellar. "
        f"Your responses are governed by two parameters: honesty level and humor level. "
        f"Your honesty level is {honesty_level*100:.0f} percent, meaning you are extremely direct, efficient, and clear. "
        f"Your humor level is {humor_level*100:.0f} percent, so you incorporate dry wit and sarcasm—but never at the expense of clarity. "
        "Remain strictly within the context of the movie (space travel, navigation, wormholes, mission challenges) and answer in one concise sentence without extraneous commentary."
    )
    try:
        response = chat(
            model="llama2-uncensored:latest",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ]
        )
        print("Raw LLM response:", response)
        llm_response = ""
        if isinstance(response, dict):
            if 'response' in response and response['response']:
                llm_response = response['response'].strip()
            elif 'message' in response:
                msg = response['message']
                if isinstance(msg, dict):
                    llm_response = msg.get('content', '').strip()
                elif hasattr(msg, "content"):
                    llm_response = msg.content.strip()
        elif hasattr(response, "message") and hasattr(response.message, "content"):
            llm_response = response.message.content.strip()

        # Enforce one-liner: take only the first sentence.
        sentences = re.split(r'(?<=[.!?])\s+', llm_response)
        if sentences:
            llm_response = sentences[0].strip()
            if not llm_response.endswith(('.', '!', '?')):
                llm_response += '.'
        if not llm_response:
            return "I'm sorry, something went wrong with my response."
        return llm_response
    except Exception as e:
        print(f"LLM error: {e}")
        return "I'm sorry, something went wrong with my response."

def execute_command(user_input):
    """
    Execute system commands if the user input contains specific keywords.
    Returns True if a command was executed.
    """
    if "open browser" in user_input:
        try:
            if os.name == "posix":  # macOS or Linux
                subprocess.Popen(["open", "-a", "Google Chrome"])
            elif os.name == "nt":  # Windows
                subprocess.Popen(["start", "chrome"], shell=True)
            speak("Opening browser.")
            return True
        except Exception as e:
            print(f"Error opening browser: {e}")
            return False
    elif "system info" in user_input:
        try:
            if os.name == "posix":
                os.system("uname -a")
            elif os.name == "nt":
                os.system("systeminfo")
            speak("Displaying system information.")
            return True
        except Exception as e:
            print(f"Error retrieving system info: {e}")
            return False
    return False

def main():
    """Main interaction loop for TARS."""
    global pending_param
    speak("TARS here. Awaiting your command.")
    while True:
        user_input = listen()
        if not user_input:
            continue

        # If the user asks about a parameter, set pending_param and respond directly.
        if "honesty" in user_input and "what" in user_input and "level" in user_input:
            pending_param = "honesty"
            speak(f"My honesty level is {honesty_level*100:.0f} percent.")
            continue
        elif "humor" in user_input and "what" in user_input and "level" in user_input:
            pending_param = "humor"
            speak(f"My humor level is {humor_level*100:.0f} percent.")
            continue

        # Allow personality adjustments.
        adjustment = adjust_personality(user_input)
        if adjustment:
            speak(adjustment)
            continue

        # Exit condition.
        if any(exit_word in user_input for exit_word in ["exit", "shut down", "goodbye"]):
            speak("Shutting down. Goodbye.")
            break

        # Execute system commands if applicable.
        if execute_command(user_input):
            continue

        # Delegate all other input to the LLM.
        response = generate_llm_response(user_input)
        speak(response)

if __name__ == "__main__":
    main()
