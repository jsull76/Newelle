from abc import abstractmethod
from subprocess import check_output
import os, sys, json
import importlib
from typing import Any, Callable
import pyaudio
import wave
import speech_recognition as sr
from .extra import find_module, install_module
from .handler import Handler
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class AudioRecorder:
    """Record audio"""
    def __init__(self):
        self.recording = False
        self.frames = []
        self.sample_format = pyaudio.paInt16
        self.channels = 1
        self.sample_rate = 44100
        self.chunk_size = 1024

    def start_recording(self):
        self.recording = True
        self.frames = []
        try:
            p = pyaudio.PyAudio()
            stream = p.open(format=self.sample_format,
                            channels=self.channels,
                            rate=self.sample_rate,
                            frames_per_buffer=self.chunk_size,
                            input=True)
            while self.recording:
                data = stream.read(self.chunk_size)
                self.frames.append(data)
            stream.stop_stream()
            stream.close()
            p.terminate()
        except Exception as e:
            logging.error(f"Error during recording: {e}")
            self.recording = False

    def stop_recording(self, output_file: str):
        self.recording = False
        try:
            p = pyaudio.PyAudio()
            wf = wave.open(output_file, 'wb')
            wf.setnchannels(self.channels)
            wf.setsampwidth(p.get_sample_size(self.sample_format))
            wf.setframerate(self.sample_rate)
            wf.writeframes(b''.join(self.frames))
            wf.close()
            p.terminate()
        except Exception as e:
            logging.error(f"Error saving recording: {e}")


class STTHandler(Handler):
    """Every STT Handler should extend this class"""
    key: str = ""
    schema_key: str = "stt-settings"

    def is_installed(self) -> bool:
        for module in self.get_extra_requirements():
            if find_module(module) is None:
                return False
        return True

    @abstractmethod
    def recognize_file(self, path: str) -> str | None:
        """Recognize a given audio file"""
        pass


class SphinxHandler(STTHandler):
    key: str = "Sphinx"

    @staticmethod
    def get_extra_requirements() -> List[str]:
        return ["pocketsphinx"]

    def recognize_file(self, path: str) -> str | None:
        r = sr.Recognizer()
        try:
            with sr.AudioFile(path) as source:
                audio = r.record(source)
            res = r.recognize_sphinx(audio)
            return res
        except sr.UnknownValueError:
            logging.info("Could not understand audio")
            return _("Could not understand the audio")
        except Exception as e:
            logging.error(f"Error recognizing audio with Sphinx: {e}")
            return None


class GoogleSRHandler(STTHandler):
    key: str = "google_sr"

    def get_extra_settings(self) -> List[Dict]:
        return [
            {
                "key": "api",
                "title": _("API Key"),
                "description": _("API Key for Google SR, write 'default' to use the default one"),
                "type": "entry",
                "default": "default"
            },
            {
                "key": "language",
                "title": _("Language"),
                "description": _("The language of the text to recgnize in IETF"),
                "type": "entry",
                "default": "en-US",
                "website": "https://stackoverflow.com/questions/14257598/what-are-language-codes-in-chromes-implementation-of-the-html5-speech-recogniti"
            }
        ]

    def recognize_file(self, path: str) -> str | None:
        r = sr.Recognizer()
        try:
            with sr.AudioFile(path) as source:
                audio = r.record(source)
            key: str = self.get_setting("api")
            language: str = self.get_setting("language")
            res: str = r.recognize_google(audio, key=key if key != "default" else None, language=language)
            return res
        except sr.UnknownValueError:
            logging.info("Could not understand audio")
            return None
        except Exception as e:
            logging.error(f"Error recognizing audio with Google: {e}")
            return None


class WitAIHandler(STTHandler):
    key: str = "witai"

    def get_extra_settings(self) -> List[Dict]:
        return [
            {
                "key": "api",
                "title": _("API Key"),
                "description": _("Server Access Token for wit.ai"),
                "type": "entry",
                "default": ""
            },
        ]

    def recognize_file(self, path: str) -> str | None:
        r = sr.Recognizer()
        try:
            with sr.AudioFile(path) as source:
                audio = r.record(source)
            key: str = self.get_setting("api")
            res: str = r.recognize_wit(audio, key=key)
            return res
        except sr.UnknownValueError:
            logging.info("Could not understand audio")
            return None
        except Exception as e:
            logging.error(f"Error recognizing audio with Wit.ai: {e}")
            return None


class VoskHandler(STTHandler):
    key: str = "vosk"

    @staticmethod
    def get_extra_requirements() -> List[str]:
        return ["vosk"]

    def get_extra_settings(self) -> List[Dict]:
        return [
            {
                "key": "path",
                "title": _("Model Path"),
                "description": _("Absolute path to the VOSK model (unzipped)"),
                "type": "entry",
                "website": "https://alphacephei.com/vosk/models",
                "default": ""
            },
        ]

    def recognize_file(self, path: str) -> str | None:
        from vosk import Model
        r = sr.Recognizer()
        try:
            with sr.AudioFile(path) as source:
                audio = r.record(source)
            path: str = self.get_setting("path")
            r.vosk_model = Model(path)
            res: str = json.loads(r.recognize_vosk(audio))["text"]
            return res
        except sr.UnknownValueError:
            logging.info("Could not understand audio")
            return None
        except Exception as e:
            logging.error(f"Error recognizing audio with Vosk: {e}")
            return None


class WhisperAPIHandler(STTHandler):
    key: str = "whisperapi"

    @staticmethod
    def get_extra_requirements() -> List[str]:
        return ["openai"]

    def get_extra_settings(self) -> List[Dict]:
        return [
            {
                "key": "api",
                "title": _("API Key"),
                "description": _("API Key for OpenAI"),
                "type": "entry",
                "default": ""
            },
            {
                "key": "model",
                "title": _("Whisper API Model"),
                "description": _("Name of the Whisper API Model"),
                "type": "entry",
                "default": "whisper-1"
            },
        ]

    def recognize_file(self, path: str) -> str | None:
        r = sr.Recognizer()
        try:
            with sr.AudioFile(path) as source:
                audio = r.record(source)
            model: str = self.get_setting("model")
            api: str = self.get_setting("api")
            res: str = r.recognize_whisper_api(audio, model=model, api_key=api)
            return res
        except sr.UnknownValueError:
            logging.info("Could not understand audio")
            return None
        except Exception as e:
            logging.error(f"Error recognizing audio with Whisper API: {e}")
            return None


class CustomSRHandler(STTHandler):
    key: str = "custom_command"

    def get_extra_settings(self) -> List[Dict]:
        return [
            {
                "key": "command",
                "title": _("Command to execute"),
                "description": _("{0} will be replaced with the model fullpath"),
                "type": "entry",
                "default": ""
            },
        ]

    @staticmethod
    def requires_sandbox_escape() -> bool:
        return True

    def recognize_file(self, path: str) -> str | None:
        command: str = self.get_setting("command")
        if command:
            try:
                res: str = check_output(["flatpak-spawn", "--host", "bash", "-c", command.replace("{0}", path)], text=True).strip()
                return res
            except Exception as e:
                logging.error(f"Error executing custom command: {e}")
                return None
        return None
