from abc import abstractmethod
from subprocess import PIPE, Popen, check_output
import os, threading
from typing import Callable, Any, Dict, List
import time, json

from g4f.Provider.selenium.Phind import quote
from openai import NOT_GIVEN
import g4f
from g4f.Provider import RetryProvider
from gi.repository.Gtk import ResponseType

from .extra import find_module, install_module, quote_string
from .handler import Handler
import requests
from bs4 import BeautifulSoup
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class LLMHandler(Handler):
    """Every LLM model handler should extend this class."""
    history: List[Dict] = []
    prompts: List[str] = []
    schema_key: str = "llm-settings"

    def __init__(self, settings: object, path: str):
        super().__init__(settings, path)
        self.web_search_enabled = self.get_setting("web_search_enabled") or False

    def stream_enabled(self) -> bool:
        """Return if the LLM supports token streaming"""
        enabled = self.get_setting("streaming")
        return enabled if enabled is not None else False

    def load_model(self, model: str) -> bool:
        """Load the specified model."""
        return True

    def set_history(self, prompts: List[str], window: object):
        """Set the current history and prompts."""
        self.prompts = prompts
        self.history = window.chat[len(window.chat) - window.memory:len(window.chat) - 1]

    def get_default_setting(self, key: str) -> Any:
        """Get the default setting from a certain key."""
        extra_settings = self.get_extra_settings()
        default_settings = {s["key"]: s["default"] for s in extra_settings}
        return default_settings.get(key)

    @abstractmethod
    def generate_text(self, prompt: str, history: List[Dict] = [], system_prompt: List[str] = []) -> str:
        """Generate text from the given prompt, history, and system prompt."""
        pass

    @abstractmethod
    def generate_text_stream(self, prompt: str, history: List[Dict] = [], system_prompt: List[str] = [],
                             on_update: Callable[[str], Any] = lambda _: None, extra_args: List = []) -> str:
        """Generate text stream from the given prompt, history, and system prompt."""
        pass

    def send_message(self, window: object, message: str) -> str:
        """Send a message to the bot."""
        if self.web_search_enabled:
            web_search_result = self.perform_web_search(message)
            if web_search_result:
                message = message + "\n\nWeb Search Results:\n" + web_search_result
        return self.generate_text(message, self.history, self.prompts)

    def send_message_stream(self, window: object, message: str, on_update: Callable[[str], Any] = lambda _: None,
                            extra_args: List = []) -> str:
        """Send a message to the bot using streaming."""
        if self.web_search_enabled:
            web_search_result = self.perform_web_search(message)
            if web_search_result:
                message = message + "\n\nWeb Search Results:\n" + web_search_result
        return self.generate_text_stream(message, self.history, self.prompts, on_update, extra_args)

    def get_suggestions(self, request_prompt: str = "", amount: int = 1) -> List[str]:
        """Get suggestions for the current chat."""
        result: List[str] = []
        history: str = ""
        for message in self.history[-4:] if len(self.history) >= 4 else self.history:
            history += message["User"] + ": " + message["Message"] + "\n"
        for i in range(0, amount):
            generated = self.generate_text(history + "\n\n" + request_prompt)
            generated = generated.replace("```json", "").replace("```", "")
            try:
                j = json.loads(generated)
                if isinstance(j, list):
                    for suggestion in j:
                        if isinstance(suggestion, str):
                            result.append(suggestion)
                            i += 1
                            if i >= amount:
                                break
            except json.JSONDecodeError as e:
                logging.error(f"Error decoding JSON response: {e}")
        return result

    def generate_chat_name(self, request_prompt: str = "") -> str:
        """Generate name of the current chat."""
        return self.generate_text(request_prompt, self.history)

    def perform_web_search(self, query: str) -> str:
        """Perform a web search using Google."""
        try:
            url = f"https://www.google.com/search?q={query}"
            response = requests.get(url)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")
            results = []
            for result in soup.find_all("div", class_="g"):
                link = result.find("a", href=True)
                if link:
                    title = link.text.strip()
                    url = link["href"]
                    snippet = result.find("div", class_="s")
                    summary = snippet.text.strip().split('. ')[0] + "." if snippet else ""
                    results.append(f"- {title} ({url})\nSummary: {summary}\n")
            return "".join(results)
        except requests.exceptions.RequestException as e:
            logging.error(f"Error performing web search: {e}")
            return f"Error performing web search: {e}"
        except Exception as e:
            logging.error(f"Error processing web search results: {e}")
            return f"Error processing web search results: {e}"


class G4FHandler(LLMHandler):
    """Common methods for g4f models"""
    key: str = "g4f"

    @staticmethod
    def get_extra_requirements() -> List[str]:
        return ["g4f"]

    def get_extra_settings(self) -> List[Dict]:
        return [
            {
                "key": "streaming",
                "title": _("Message Streaming"),
                "description": _("Gradually stream message output"),
                "type": "toggle",
                "default": True,
            },
            {
                "key": "web_search_enabled",
                "title": _("Enable Web Search"),
                "description": _("Enable web search for answers"),
                "type": "toggle",
                "default": False,
            },
        ]

    def convert_history(self, history: List[Dict], prompts: List[str] | None = None) -> List[Dict]:
        prompts = prompts or self.prompts
        result: List[Dict] = []
        result.append({"role": "system", "content": "\n".join(prompts)})
        for message in history:
            result.append({
                "role": message["User"].lower() if message["User"] in {"Assistant", "User"} else "system",
                "content": message["Message"]
            })
        return result

    def set_history(self, prompts: List[str], window: object):
        self.history = window.chat[len(window.chat) - window.memory:len(window.chat) - 1]
        self.prompts = prompts

    def generate_text(self, prompt: str, history: List[Dict] = [], system_prompt: List[str] = []) -> str:
        model: str = self.get_setting("model")
        message: str = prompt
        history: List[Dict] = self.convert_history(history, system_prompt)
        user_prompt: Dict = {"role": "user", "content": message}
        history.append(user_prompt)
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=history,
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.error(f"Error generating text: {e}")
            return f"Error: {e}"

    def generate_text_stream(self, prompt: str, history: List[Dict] = [], system_prompt: List[str] = [],
                             on_update: Callable[[str], Any] = lambda _: None, extra_args: List = []) -> str:
        model: str = self.get_setting("model")
        message: str = prompt
        history: List[Dict] = self.convert_history(history, system_prompt)
        user_prompt: Dict = {"role": "user", "content": message}
        history.append(user_prompt)
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=history,
                stream=True,
            )
            full_message: str = ""
            prev_message: str = ""
            for chunk in response:
                if chunk.choices[0].delta.content:
                    full_message += chunk.choices[0].delta.content
                    args = (full_message.strip(),) + tuple(extra_args)
                    if len(full_message) - len(prev_message) > 1:
                        on_update(*args)
                        prev_message = full_message
            return full_message.strip()
        except Exception as e:
            logging.error(f"Error generating text stream: {e}")
            return f"Error: {e}"


class NexraHandler(G4FHandler):
    key: str = "nexra"

    def __init__(self, settings: object, path: str):
        import g4f
        super().__init__(settings, path)
        self.client = g4f.client.Client(provider=g4f.Provider.Nexra)

    def get_extra_settings(self) -> List[Dict]:
        return [
            {
                "key": "model",
                "title": _("Model"),
                "description": _("The model to use"),
                "type": "combo",
                "values": (("gpt-4", "gpt-4"), ("gpt-4o", "gpt-4o"), ("gpt-3.5-turbo", "gpt-3.5-turbo"),
                           ("gpt-3", "gpt-3"), ("llama-3.1", "llama-3.1"), ("gemini-pro", "gemini-pro")),
                "default": "gpt-4o",
            }
        ] + super().get_extra_settings()


class AirforceHandler(G4FHandler):
    key: str = "airforce"

    def __init__(self, settings: object, path: str):
        import g4f
        super().__init__(settings, path)
        self.client = g4f.client.Client(provider=g4f.Provider.Airforce)
        self.models = tuple()
        for model in g4f.Provider.Airforce.models:
            if "flux" not in model and "dall-e" not in model and "any-dark" not in model and "cosmosrp" not in model:
                self.models += ((model, model),)

    def get_extra_settings(self) -> List[Dict]:
        return [
            {
                "key": "model",
                "title": _("Model"),
                "description": _("The model to use"),
                "type": "combo",
                "values": self.models,
                "default": "llama-3-70b-chat",
            }
        ] + super().get_extra_settings()


class GPT3AnyHandler(G4FHandler):
    """Use any GPT3.5-Turbo providers"""
    key: str = "GPT3Any"

    def __init__(self, settings: object, path: str):
        import g4f
        super().__init__(settings, path)
        good_providers = [g4f.Provider.DDG, g4f.Provider.MagickPen, g4f.Provider.Binjie, g4f.Provider.Pizzagpt,
                          g4f.Provider.Nexra, g4f.Provider.Koala]
        good_nongpt_providers = [g4f.Provider.ReplicateHome, g4f.Provider.Airforce, g4f.Provider.ChatGot,
                                 g4f.Provider.FreeChatgpt]
        acceptable_providers = [g4f.Provider.Allyfy, g4f.Provider.Blackbox, g4f.Provider.Upstage, g4f.Provider.ChatHub]
        self.client = g4f.client.Client(
            provider=RetryProvider([RetryProvider(good_providers), RetryProvider(good_nongpt_providers),
                                     RetryProvider(acceptable_providers)], shuffle=False))
        self.n = 0

    def generate_text(self, prompt: str, history: List[Dict] = [], system_prompt: List[str] = []) -> str:
        message: str = prompt
        history: List[Dict] = self.convert_history(history, system_prompt)
        user_prompt: Dict = {"role": "user", "content": message}
        history.append(user_prompt)
        try:
            response = self.client.chat.completions.create(
                model="",
                messages=history,
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.error(f"Error generating text: {e}")
            return f"Error: {e}"

    def generate_text_stream(self, prompt: str, history: List[Dict] = [], system_prompt: List[str] = [],
                             on_update: Callable[[str], Any] = lambda _: None, extra_args: List = []) -> str:
        message: str = prompt
        history: List[Dict] = self.convert_history(history, system_prompt)
        user_prompt: Dict = {"role": "user", "content": message}
        history.append(user_prompt)
        try:
            response = self.client.chat.completions.create(
                model="",
                messages=history,
                stream=True,
            )
            full_message: str = ""
            prev_message: str = ""
            for chunk in response:
                if chunk.choices[0].delta.content:
                    full_message += chunk.choices[0].delta.content
                    args = (full_message.strip(),) + tuple(extra_args)
                    if len(full_message) - len(prev_message) > 1:
                        on_update(*args)
                        prev_message = full_message
            return full_message.strip()
        except Exception as e:
            logging.error(f"Error generating text stream: {e}")
            return f"Error: {e}"

    def generate_chat_name(self, request_prompt: str = "") -> str:
        history: str = ""
        for message in self.history[-4:] if len(self.history) >= 4 else self.history:
            history += message["User"] + ": " + message["Message"] + "\n"
        name: str = self.generate_text(history + "\n\n" + request_prompt)
        return name


class GeminiHandler(LLMHandler):
    key: str = "gemini"
    """Official Google Gemini APIs"""

    @staticmethod
    def get_extra_requirements() -> List[str]:
        return ["google-generativeai"]

    def is_installed(self) -> bool:
        return find_module("google.generativeai") is not None

    def get_extra_settings(self) -> List[Dict]:
        return [
            {
                "key": "apikey",
                "title": _("API Key (required)"),
                "description": _("API Key got from ai.google.dev"),
                "type": "entry",
                "default": ""
            },
            {
                "key": "model",
                "title": _("Model"),
                "description": _("AI Model to use, available: gemini-1.5-pro, gemini-1.0-pro, gemini-1.5-flash"),
                "type": "combo",
                "default": "gemini-1.5-flash",
                "values": [("gemini-1.5-flash", "gemini-1.5-flash"), ("gemini-1.0-pro", "gemini-1.0-pro"),
                           ("gemini-1.5-pro", "gemini-1.5-pro")]
            },
            {
                "key": "streaming",
                "title": _("Message Streaming"),
                "description": _("Gradually stream message output"),
                "type": "toggle",
                "default": True
            },
            {
                "key": "safety",
                "title": _("Enable safety settings"),
                "description": _("Enable google safety settings to avoid generating harmful content"),
                "type": "toggle",
                "default": True
            }
        ] + super().get_extra_settings()

    def __convert_history(self, history: List[Dict]) -> List[Dict]:
        result: List[Dict] = []
        for message in history:
            result.append({
                "role": message["User"].lower() if message["User"] == "User" else "model",
                "parts": message["Message"]
            })
        return result

    def generate_text(self, prompt: str, history: List[Dict] = [], system_prompt: List[str] = []) -> str:
        import google.generativeai as genai
        from google.generativeai.protos import HarmCategory
        from google.generativeai.types import HarmBlockThreshold

        safety = None if self.get_setting("safety") else {
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        }

        genai.configure(api_key=self.get_setting("apikey"))
        instructions: str | None = "\n" + "\n".join(system_prompt) if system_prompt else None
        model = genai.GenerativeModel(self.get_setting("model"), system_instruction=instructions, safety_settings=safety)
        converted_history: List[Dict] = self.__convert_history(history)
        try:
            chat = model.start_chat(
                history=converted_history
            )
            response = chat.send_message(prompt)
            return response.text
        except Exception as e:
            logging.error(f"Error generating text with Gemini: {e}")
            return "Message blocked: " + str(e)

    def generate_text_stream(self, prompt: str, history: List[Dict] = [], system_prompt: List[str] = [],
                             on_update: Callable[[str], Any] = lambda _: None, extra_args: List = []) -> str:
        import google.generativeai as genai
        from google.generativeai.protos import HarmCategory
        from google.generativeai.types import HarmBlockThreshold

        safety = None if self.get_setting("safety") else {
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        }

        genai.configure(api_key=self.get_setting("apikey"))
        instructions: str | None = "\n".join(system_prompt) if system_prompt else None
        model = genai.GenerativeModel(self.get_setting("model"), system_instruction=instructions, safety_settings=safety)
        converted_history: List[Dict] = self.__convert_history(history)
        try:
            chat = model.start_chat(history=converted_history)
            response = chat.send_message(prompt, stream=True)
            full_message: str = ""
            for chunk in response:
                full_message += chunk.text
                args = (full_message.strip(),) + tuple(extra_args)
                on_update(*args)
            return full_message.strip()
        except Exception as e:
            logging.error(f"Error generating text stream with Gemini: {e}")
            return "Message blocked: " + str(e)


class CustomLLMHandler(LLMHandler):
    key: str = "custom_command"

    @staticmethod
    def requires_sandbox_escape() -> bool:
        return True

    def get_extra_settings(self) -> List[Dict]:
        return [
            {
                "key": "streaming",
                "title": _("Message Streaming"),
                "description": _("Gradually stream message output"),
                "type": "toggle",
                "default": True
            },
            {
                "key": "web_search_enabled",
                "title": _("Enable Web Search"),
                "description": _("Enable web search for answers"),
                "type": "toggle",
                "default": False,
            },

            {
                "key": "command",
                "title": _("Command to execute to get bot output"),
                "description": _(
                    "Command to execute to get bot response, {0} will be replaced with a JSON file containing the chat, {1} with the system prompt"),
                "type": "entry",
                "default": ""
            },
            {
                "key": "suggestion",
                "title": _("Command to execute to get bot's suggestions"),
                "description": _(
                    "Command to execute to get chat suggestions, {0} will be replaced with a JSON file containing the chat, {1} with the extra prompts, {2} with the numer of suggestions to generate. Must return a JSON array containing the suggestions as strings"),
                "type": "entry",
                "default": ""
            },

        ]

    def set_history(self, prompts: List[str], window: object):
        self.history = window.chat[len(window.chat) - window.memory:len(window.chat)]
        self.prompts = prompts

    def generate_text(self, prompt: str, history: List[Dict] = [], system_prompt: List[str] = []) -> str:
        command: str = self.get_setting("command")
        command = command.replace("{0}", quote_string(json.dumps(self.history)))
        command = command.replace("{1}", quote_string(json.dumps(self.prompts)))
        try:
            out = check_output(["flatpak-spawn", "--host", "bash", "-c", command], text=True)
            return out.strip()
        except Exception as e:
            logging.error(f"Error executing custom command: {e}")
            return f"Error: {e}"

    def get_suggestions(self, request_prompt: str = "", amount: int = 1) -> List[str]:
        command: str = self.get_setting("suggestion")
        if not command:
            return []
        command = command.replace("{0}", quote_string(json.dumps(self.history)))
        command = command.replace("{1}", quote_string(json.dumps(self.prompts)))
        command = command.replace("{2}", str(amount))
        try:
            out = check_output(["flatpak-spawn", "--host", "bash", "-c", command], text=True)
            return json.loads(out.strip())
        except Exception as e:
            logging.error(f"Error getting suggestions from custom command: {e}")
            return []

    def generate_text_stream(self, prompt: str, history: List[Dict] = [], system_prompt: List[str] = [],
                             on_update: Callable[[str], Any] = lambda _: None, extra_args: List = []) -> str:
        command: str = self.get_setting("command")
        command = command.replace("{0}", quote_string(json.dumps(self.history)))
        command = command.replace("{1}", quote_string(json.dumps(self.prompts)))
        try:
            process = Popen(["flatpak-spawn", "--host", "bash", "-c", command], stdout=PIPE, text=True)
            full_message: str = ""
            prev_message: str = ""
            while True:
                chunk = process.stdout.readline()
                if not chunk:
                    break
                full_message += chunk
                args = (full_message.strip(),) + tuple(extra_args)
                if len(full_message) - len(prev_message) > 1:
                    on_update(*args)
                    prev_message = full_message
            process.wait()
            return full_message.strip()
        except Exception as e:
            logging.error(f"Error generating text stream from custom command: {e}")
            return f"Error: {e}"


class OllamaHandler(LLMHandler):
    key: str = "ollama"

    @staticmethod
    def get_extra_requirements() -> List[str]:
        return ["ollama"]

    def get_extra_settings(self) -> List[Dict]:
        return [
            {
                "key": "endpoint",
                "title": _("API Endpoint"),
                "description": _("API base url, change this to use interference APIs"),
                "type": "entry",
                "default": "http://localhost:11434"
            },
            {
                "key": "model",
                "title": _("Ollama Model"),
                "description": _("Name of the Ollama Model"),
                "type": "entry",
                "default": "llama3.1:8b"
            },
            {
                "key": "streaming",
                "title": _("Message Streaming"),
                "description": _("Gradually stream message output"),
                "type": "toggle",
                "default": True
            },
            {
                "key": "web_search_enabled",
                "title": _("Enable Web Search"),
                "description": _("Enable web search for answers"),
                "type": "toggle",
                "default": False,
            },
        ]

    def convert_history(self, history: List[Dict], prompts: List[str] | None = None) -> List[Dict]:
        prompts = prompts or self.prompts
        result: List[Dict] = []
        result.append({"role": "system", "content": "\n".join(prompts)})
        for message in history:
            result.append({
                "role": message["User"].lower() if message["User"] in {"Assistant", "User"} else "system",
                "content": message["Message"]
            })
        return result

    def generate_text(self, prompt: str, history: List[Dict] = [], system_prompt: List[str] = []) -> str:
        from ollama import Client
        messages: List[Dict] = self.convert_history(history, system_prompt)
        messages.append({"role": "user", "content": prompt})

        client = Client(
            host=self.get_setting("endpoint")
        )
        try:
            response = client.chat(
                model=self.get_setting("model"),
                messages=messages,
            )
            return response["message"]["content"]
        except Exception as e:
            logging.error(f"Error generating text with Ollama: {e}")
            return str(e)

    def generate_text_stream(self, prompt: str, history: List[Dict] = [], system_prompt: List[str] = [],
                             on_update: Callable[[str], Any] = lambda _: None, extra_args: List = []) -> str:
        from ollama import Client
        messages: List[Dict] = self.convert_history(history, system_prompt)
        messages.append({"role": "user", "content": prompt})
        client = Client(
            host=self.get_setting("endpoint")
        )
        try:
            response = client.chat(
                model=self.get_setting("model"),
                messages=messages,
                stream=True
            )
            full_message: str = ""
            prev_message: str = ""
            for chunk in response:
                full_message += chunk["message"]["content"]
                args = (full_message.strip(),) + tuple(extra_args)
                if len(full_message) - len(prev_message) > 1:
                    on_update(*args)
                    prev_message = full_message
            return full_message.strip()
        except Exception as e:
            logging.error(f"Error generating text stream with Ollama: {e}")
            return str(e)


class OpenAIHandler(LLMHandler):
    key: str = "openai"

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
                "key": "endpoint",
                "title": _("API Endpoint"),
                "description": _("API base url, change this to use interference APIs"),
                "type": "entry",
                "default": "https://api.openai.com/v1/"
            },
            {
                "key": "model",
                "title": _("OpenAI Model"),
                "description": _("Name of the OpenAI Model"),
                "type": "entry",
                "default": "gpt-3.5-turbo"
            },
            {
                "key": "streaming",
                "title": _("Message Streaming"),
                "description": _("Gradually stream message output"),
                "type": "toggle",
                "default": True
            },
            {
                "key": "advanced_params",
                "title": _("Advanced Parameters"),
                "description": _("Include parameters like Max Tokens, Top-P, Temperature, etc."),
                "type": "toggle",
                "default": True
            },
            {
                "key": "max-tokens",
                "title": _("Max Tokens"),
                "description": _("Max tokens of the generated text"),
                "website": "https://help.openai.com/en/articles/4936856-what-are-tokens-and-how-to-count-them",
                "type": "range",
                "min": 3,
                "max": 400,
                "default": 150,
                "round-digits": 0
            },
            {
                "key": "top-p",
                "title": _("Top-P"),
                "description": _("An alternative to sampling with temperature, called nucleus sampling"),
                "website": "https://platform.openai.com/docs/api-reference/completions/create#completions/create-top_p",
                "type": "range",
                "min": 0,
                "max": 1,
                "default": 1,
                "round-digits": 2,
            },
            {
                "key": "temperature",
                "title": _("Temperature"),
                "description": _("What sampling temperature to use. Higher values will make the output more random"),
                "website": "https://platform.openai.com/docs/api-reference/completions/create#completions/create-temperature",
                "type": "range",
                "min": 0,
                "max": 2,
                "default": 1,
                "round-digits": 2,
            },
            {
                "key": "frequency-penalty",
                "title": _("Frequency Penalty"),
                "description": _(
                    "Positive values penalize new tokens based on their existing frequency in the text so far, decreasing the model's likelihood to repeat the same line"),
                "website": "https://platform.openai.com/docs/api-reference/completions/create#completions/create-frequency_penalty",
                "type": "range",
                "min": -2,
                "max": 2,
                "default": 0,
                "round-digits": 1,
            },
            {
                "key": "presence-penalty",
                "title": _("Presence Penalty"),
                "description": _(
                    "Positive values penalize new tokens based on whether they appear in the text so far, increasing the model's likelihood to talk about new topics."),
                "website": "https://platform.openai.com/docs/api-reference/completions/create#completions/create-frequency_penalty",
                "type": "range",
                "min": -2,
                "max": 2,
                "default": 0,
                "round-digits": 1,
            },
            {
                "key": "web_search_enabled",
                "title": _("Enable Web Search"),
                "description": _("Enable web search for answers"),
                "type": "toggle",
                "default": False,
            },
        ]

    def convert_history(self, history: List[Dict], prompts: List[str] | None = None) -> List[Dict]:
        prompts = prompts or self.prompts
        result: List[Dict] = []
        result.append({"role": "system", "content": "\n".join(prompts)})
        for message in history:
            result.append({
                "role": message["User"].lower() if message["User"] in {"Assistant", "User"} else "system",
                "content": message["Message"]
            })
        return result

    def generate_text(self, prompt: str, history: List[Dict] = [], system_prompt: List[str] = []) -> str:
        import openai
        openai.api_key = self.get_setting("api")
        messages: List[Dict] = self.convert_
