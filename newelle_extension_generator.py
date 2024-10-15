"""Extension generator for Newelle."""
import os
import json
from typing import Dict, Tuple, List, Callable
from .extra import validate_python_code
import logging
import re

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def generate_extension_code(extension_name: str, description: str, functionality: str, llm_handler: Callable) -> Tuple[str, bool]:
    """Generates extension code using an LLM."""
    try:
        prompt: str = f"""
Generate a Newelle extension named '{extension_name}' with the following specifications:

Description: {description}
Functionality: {functionality}

The extension should be a valid Python file that adheres to Newelle's extension guidelines.  Include necessary imports and error handling.  The extension should be self-contained and easily integrable into Newelle.

Extension Code:
```python
"""
        extension_code: str = llm_handler(prompt)
        extension_code = extension_code.replace("```python\n", "").replace("\n```", "")
        valid: bool = validate_python_code(extension_code)
        return extension_code, valid
    except Exception as e:
        logging.error(f"Error generating extension code: {e}")
        return "", False

def validate_extension_code(extension_code: str) -> bool:
    """Validates the generated extension code."""
    return validate_python_code(extension_code)

def install_extension(extension_code: str, extension_path: str) -> bool:
    """Installs the extension code."""
    #Check for invalid characters in extension name
    if not re.fullmatch(r"^[a-zA-Z0-9_]+$", extension_path.split('/')[-1]):
        logging.error(f"Invalid extension name: {extension_path.split('/')[-1]}. Only alphanumeric characters and underscores are allowed.")
        return False

    if not os.path.exists(extension_path):
        try:
            os.makedirs(extension_path)
        except OSError as e:
            logging.error(f"Error creating extension directory: {e}")
            return False
    filepath: str = os.path.join(extension_path, "main.json")
    try:
        with open(filepath, "w") as f:
            json.dump({"name": extension_path.split('/')[-1], "prompt": "", "api": extension_path.split('/')[-1] + ".py", "about": ""}, f)
        filepath: str = os.path.join(extension_path, f"{extension_path.split('/')[-1]}.py")
        with open(filepath, "w") as f:
            f.write(extension_code)
        return True
    except Exception as e:
        logging.error(f"Error writing extension files: {e}")
        return False

def load_extension(extension_path: str) -> object | None:
    """Loads an extension from the given path."""
    try:
        return None
    except Exception as e:
        logging.error(f"Error loading extension: {e}")
        return None

def get_extension_metadata(extension_path: str) -> Dict | None:
    """Retrieves extension metadata from a JSON file."""
    metadata_path: str = os.path.join(extension_path, "extension.json")
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logging.error(f"Error decoding extension metadata: {e}")
            return None
    return None
