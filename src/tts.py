from abc import abstractmethod
from typing import Any, Callable, List, Tuple, Dict
from gtts import gTTS, lang
from subprocess import check_output, CalledProcessError
import threading, time
import os, json
from .extra import can_escape_sandbox, human_readable_size
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
from pygame import mixer
from .handler import Handler
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class TTSHandler(Handler):
    """Every TTS handler should extend this class."""
    key: str = ""
    schema_key: str = "tts-voice"
    voices: Tuple[Tuple[str, str]] = ()
    _play_lock: threading.Semaphore = threading.Semaphore(1)

    def __init__(self, settings: object, path: str):
        mixer.init()
        self.settings = settings
        self.path = path
        self.voices = ()
        self.on_start: Callable = lambda: None
        self.on_stop: Callable = lambda: None

    def get_extra_settings(self) -> List[Dict]:
        voices: Tuple[Tuple[str, str]] = self.get_voices()
        default: str = "" if len(voices) == 0 else voices[0][1]
        return [
            {
                "key": "voice",
                "type": "combo",
                "title": _("Voice"),
                "description": _("Choose the preferred voice"),
                "default": default,
                "values": voices
            }
        ]

    def get_voices(self) -> Tuple[Tuple[str, str]]:
        return self.voices

    def voice_available(self, voice: str) -> bool:
        return any(l[1] == voice for l in self.get_voices())

    @abstractmethod
    def save_audio(self, message: str, file: str):
        pass

    def play_audio(self, message: str):
        file_name: str = self._generate_temp_filename()
        path: str = os.path.join(self.path, file_name)
        try:
            self.save_audio(message, path)
            self.playsound(path)
            os.remove(path)
        except Exception as e:
            logging.error(f"Error playing audio: {e}")

    def connect(self, signal: str, callback: Callable):
        if signal == "start":
            self.on_start = callback
        elif signal == "stop":
            self.on_stop = callback

    def playsound(self, path: str):
        self.stop()
        self._play_lock.acquire()
        self.on_start()
        try:
            mixer.music.load(path)
            mixer.music.play()
            while mixer.music.get_busy():
                time.sleep(0.1)
        except Exception as e:
            logging.error(f"Error playing sound: {e}")
        finally:
            self.on_stop()
            self._play_lock.release()

    def stop(self):
        if mixer.music.get_busy():
            mixer.music.stop()

    def is_installed(self) -> bool:
        return True

    def get_current_voice(self) -> str | None:
        voice: str | None = self.get_setting("voice")
        return voice if voice else (self.voices[0][1] if self.voices else None)

    def set_voice(self, voice: str):
        self.set_setting("voice", voice)

    def _generate_temp_filename(self) -> str:
        timestamp: str = str(int(time.time()))
        random_part: str = str(os.urandom(8).hex())
        return f"{timestamp}_{random_part}.mp3"


class gTTSHandler(TTSHandler):
    key: str = "gtts"

    def get_voices(self) -> Tuple[Tuple[str, str]]:
        if self.voices:
            return self.voices
        x = lang.tts_langs()
        self.voices = tuple((x[l], l) for l in x)
        return self.voices

    def save_audio(self, message: str, file: str):
        voice: str = self.get_current_voice() or self.get_voices()[0][1]
        try:
            tts = gTTS(message, lang=voice)
            tts.save(file)
        except Exception as e:
            logging.error(f"Error saving audio with gTTS: {e}")


class EspeakHandler(TTSHandler):
    key: str = "espeak"

    @staticmethod
    def requires_sandbox_escape() -> bool:
        return True

    def get_voices(self) -> Tuple[Tuple[str, str]]:
        if self.voices:
            return self.voices
        if not self.is_installed():
            return self.voices
        try:
            output: str = check_output(["flatpak-spawn", "--host", "espeak", "--voices"], text=True).strip()
            lines: List[str] = output.split("\n")[1:]
            self.voices = tuple((line.split()[3], line.split()[4]) for line in lines)
            return self.voices
        except (CalledProcessError, IndexError) as e:
            logging.error(f"Error getting espeak voices: {e}")
            return ()

    def play_audio(self, message: str):
        self._play_lock.acquire()
        try:
            check_output(["flatpak-spawn", "--host", "espeak", "-v" + str(self.get_current_voice()), message], stderr=subprocess.STDOUT, text=True)
        except CalledProcessError as e:
            logging.error(f"Error playing audio with espeak: {e}")
        finally:
            self._play_lock.release()

    def save_audio(self, message: str, file: str):
        try:
            r = check_output(["flatpak-spawn", "--host", "espeak", "-f", "-v" + str(self.get_current_voice()), message, "--stdout"], stderr=subprocess.STDOUT, text=True)
            with open(file, "w") as f:
                f.write(r)
        except CalledProcessError as e:
            logging.error(f"Error saving audio with espeak: {e}")

    def is_installed(self) -> bool:
        if not can_escape_sandbox():
            return False
        try:
            output: str = check_output(["flatpak-spawn", "--host", "whereis", "espeak"], text=True).strip()
            return ":" in output
        except CalledProcessError as e:
            logging.error(f"Error checking espeak installation: {e}")
            return False


class CustomTTSHandler(TTSHandler):
    key: str = "custom_command"

    def __init__(self, settings: object, path: str):
        super().__init__(settings, path)
        self.voices: Tuple = ()

    @staticmethod
    def requires_sandbox_escape() -> bool:
        return True

    def get_extra_settings(self) -> List[Dict]:
        return [{
            "key": "command",
            "title": _("Command to execute"),
            "description": _("{0} will be replaced with the text to speak"),
            "type": "entry",
            "default": ""
        }]

    def is_installed(self) -> bool:
        return True

    def play_audio(self, message: str):
        command: str | None = self.get_setting("command")
        if command:
            self._play_lock.acquire()
            try:
                check_output(["flatpak-spawn", "--host", "bash", "-c", command.replace("{0}", message)], stderr=subprocess.STDOUT, text=True)
            except CalledProcessError as e:
                logging.error(f"Error executing custom TTS command: {e}")
            finally:
                self._play_lock.release()
