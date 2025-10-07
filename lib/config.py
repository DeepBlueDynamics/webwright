import os
from configparser import ConfigParser
from prompt_toolkit.shortcuts import input_dialog, radiolist_dialog, yes_no_dialog
import google.generativeai as genai
from openai import OpenAI
import anthropic
from github import Github
from coolname import generate_slug
from lib.util import get_logger
from functools import lru_cache

logger = get_logger()

ANTHROPIC_MODELS = [
    ("claude-3-opus-20240229", "Claude 3 Opus"),
    ("claude-3-sonnet-20240229", "Claude 3 Sonnet"),
    ("claude-3-haiku-20240307", "Claude 3 Haiku"),
    ("claude-3-5-sonnet-20240620", "Claude 3.5 Sonnet")
]

GEMINI_MODELS = [
    ("gemini-1.5-pro", "Gemini 1.5 Pro"),
    ("gemini-1.5-flash", "Gemini 1.5 Flash"),
    ("gemini-1.0-pro", "Gemini 1.0 Pro"),
]

OLLAMA_MODELS = [
    ("llama2", "Llama 2"),
    ("mistral", "Mistral"),
    ("codellama", "Code Llama"),
    ("mixtral", "Mixtral")
]

class Config:
    def __init__(self):
        self.config_dir = os.path.expanduser('~/.webwright')
        self.config_file_path = os.path.join(self.config_dir, "webwright_config")
        self.config = ConfigParser()
        self.models = []
        self.read_config()
        self.populate_models()

    def populate_models(self):
        # Add OpenAI models
        openai_token = self.get_openai_api_key()

        # Add OpenAI models if the token is available
        if openai_token:
            try:
                client = OpenAI(api_key=openai_token)
                models = client.models.list()
                self.models.extend([
                    {"name": model.id, "model": model.id, "api_service": "openai"}
                    for model in models.data
                ])
            except Exception as e:
                logger.error(f"Error fetching OpenAI models: {str(e)}")

        # Add Anthropic models
        self.models.extend([
            {"name": name, "model": model_id, "api_service": "anthropic"}
            for model_id, name in ANTHROPIC_MODELS
        ])

        # Add Gemini models
        self.models.extend([
            {"name": name, "model": model_id, "api_service": "gemini"}
            for model_id, name in GEMINI_MODELS
        ])

        # Add Ollama models
        self.models.extend([
            {"name": name, "model": model_id, "api_service": "ollama"}
            for model_id, name in OLLAMA_MODELS
        ])

        return self.models

    def ensure_config_dir_exists(self):
        os.makedirs(self.config_dir, exist_ok=True)
        
    def read_config(self):
        self.ensure_config_dir_exists()
        self.config.read(self.config_file_path)

    def write_config(self):
        self.ensure_config_dir_exists()
        with open(self.config_file_path, "w") as f:
            self.config.write(f)

    def set_config_value(self, section, key, value):
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, key, str(value))
        self.write_config()  # Write to file immediately

    def get_config_value(self, section, key):
        if self.config.has_option(section, key):
            return self.config.get(section, key)
        return None

    def reload_config(self):
        self.read_config()  # Re-read the config file

    def get_username(self):
        username = self.get_config_value("config", "username")
        if username:
            logger.info(f"You are logged in as `{username}`.")
            return username
        else:
            username = generate_slug(2)
            return self.set_username(username)

    def set_username(self, username):
        self.set_config_value("config", "username", username)
        return username
        
    def get_openai_api_key(self):
        openai_token = os.getenv("OPENAI_API_KEY") or self.get_config_value("config", "OPENAI_API_KEY")

        if openai_token == "NONE":
            return None
        
        if openai_token and self.check_openai_token(openai_token):
            return openai_token

        openai_token = input_dialog(
            title="OpenAI API Key",
            text="Enter your OpenAI API key (Enter to skip):"
        ).run()

        if openai_token == '':
            logger.info("OpenAI token entry cancelled.")
            self.set_config_value("config", "OPENAI_API_KEY", "NONE")
            return None
        
        if openai_token:
            if self.check_openai_token(openai_token):
                self.set_config_value("config", "OPENAI_API_KEY", openai_token)
                return openai_token
            else:
                logger.error("Invalid OpenAI token. Skipping.")
        return None

    @lru_cache(maxsize=1)
    def check_openai_token(self, openai_token):
        client = OpenAI(api_key=openai_token)
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": "Confirm the token is working."}],
                max_tokens=5
            )
            logger.info("OpenAI API token verified successfully.")
            return True
        except Exception as e:
            logger.error(f"Error verifying OpenAI API token: {str(e)}")
            return False

    def get_anthropic_api_key(self):
        anthropic_token = os.getenv("ANTHROPIC_API_KEY") or self.get_config_value("config", "ANTHROPIC_API_KEY")
        if anthropic_token == "NONE":
            return None
        
        if anthropic_token and self.check_anthropic_token(anthropic_token):
            return anthropic_token
        
        anthropic_token = input_dialog(
            title="Anthropic API Key",
            text="Enter your Anthropic API key (Enter to skip):"
        ).run()

        if anthropic_token == '':
            logger.info("Anthropic token entry cancelled.")
            self.set_config_value("config", "ANTHROPIC_API_KEY", "NONE")
            return None

        if anthropic_token:
            if self.check_anthropic_token(anthropic_token):
                self.set_config_value("config", "ANTHROPIC_API_KEY", anthropic_token)
                return anthropic_token
            else:
                logger.error("Invalid Anthropic token. Skipping.")
        return None

    @lru_cache(maxsize=1)
    def check_anthropic_token(self, anthropic_token):
        try:
            client = anthropic.Anthropic(api_key=anthropic_token)
            message = client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=10,
                temperature=0,
                system="Respond with 'Token verified' if this message is received.",
                messages=[
                    {
                        "role": "user",
                        "content": "Verify token"
                    }
                ]
            )
            if "Token verified" in message.content[0].text:
                logger.info("Anthropic API token verified successfully.")
                return True
            else:
                logger.error("Unexpected response from Anthropic API.")
                return False
        except Exception as e:
            logger.error(f"Error verifying Anthropic API token: {str(e)}")
            return False

    def get_gemini_api_key(self):
        gemini_token = os.getenv("GEMINI_API_KEY") or self.get_config_value("config", "GEMINI_API_KEY")
        if gemini_token == "NONE":
            return None
        
        if gemini_token and self.check_gemini_token(gemini_token):
            return gemini_token
        
        gemini_token = input_dialog(
            title="Gemini API Key",
            text="Enter your Gemini API key (Enter to skip):"
        ).run()

        if gemini_token == '':
            logger.info("Gemini token entry cancelled.")
            self.set_config_value("config", "GEMINI_API_KEY", "NONE")
            return None

        if gemini_token:
            if self.check_gemini_token(gemini_token):
                self.set_config_value("config", "GEMINI_API_KEY", gemini_token)
                return gemini_token
            else:
                logger.error("Invalid Gemini token. Skipping.")
        return None
    
    @lru_cache(maxsize=1)
    def check_gemini_token(self, gemini_token):
        try:
            genai.configure(api_key=gemini_token)
            model = genai.GenerativeModel('gemini-1.5-pro')
            response = model.generate_content("Confirm the token is working.")
            logger.info("Gemini API token verified successfully.")
            return True
        except Exception as e:
            logger.error(f"Error verifying Gemini API token: {str(e)}")
            return False

    def get_ollama_endpoint(self):
        endpoint = os.getenv("OLLAMA_API_ENDPOINT") or self.get_config_value("config", "OLLAMA_API_ENDPOINT")
        if not endpoint:
            endpoint = input_dialog(
                title="Ollama API Endpoint",
                text="Enter Ollama API endpoint (local or substrate.run, Enter for default):"
            ).run()
            if not endpoint:
                endpoint = "http://localhost:11434"  # Default local endpoint
            self.set_config_value("config", "OLLAMA_API_ENDPOINT", endpoint)
        return endpoint
        
    def determine_api_to_use(self):
        preferred_api = self.get_config_value("config", "PREFERRED_API")

        openai_token = self.get_openai_api_key()
        anthropic_token = self.get_anthropic_api_key()

        openai_model = self.get_config_value("config", "OPENAI_MODEL")
        anthropic_model = self.get_config_value("config", "ANTHROPIC_MODEL")
        ollama_model = self.get_config_value("config", "OLLAMA_MODEL")

        available_apis = []

        if openai_token and openai_token != "NONE":
            if not openai_model or openai_model == "NONE":
                openai_model = self.select_openai_model(api_key=openai_token)
            if openai_model:
                available_apis.append(("openai", f"OpenAI ({openai_model})"))

        if anthropic_token and anthropic_token != "NONE":
            if not anthropic_model or anthropic_model == "NONE":
                anthropic_model = self.select_anthropic_model()
            if anthropic_model:
                available_apis.append(("anthropic", f"Anthropic ({anthropic_model})"))

        # Detect Ollama availability (local default or configured endpoint)
        ollama_endpoint = os.getenv("OLLAMA_API_ENDPOINT") or self.get_config_value("config", "OLLAMA_API_ENDPOINT")
        if ollama_endpoint == "NONE":
            ollama_endpoint = None

        if ollama_endpoint:
            if not ollama_model or ollama_model in ("", "NONE", None):
                ollama_model = "llama3"
            available_apis.append(("ollama", f"Ollama ({ollama_model})"))
        elif not available_apis:
            # No remote APIs configured; fall back to attempting local Ollama
            try:
                ollama_endpoint = self.get_ollama_endpoint()
                if ollama_endpoint:
                    if not ollama_model or ollama_model in ("", "NONE", None):
                        ollama_model = "llama3"
                    available_apis.append(("ollama", f"Ollama ({ollama_model})"))
            except Exception as e:
                logger.error(f"Unable to configure Ollama endpoint: {e}")

        if not available_apis:
            logger.error("Error: No AI providers are available.")
            try:
                should_exit = yes_no_dialog(
                    title="Exit Program",
                    text="Can't proceed without valid AI provider configurations. Edit your ~/.webwright/webwright_config file to set the API configuration(s). Exit program?"
                ).run()
                if should_exit:
                    return None, None, None, None
                else:
                    return self.determine_api_to_use()
            except RuntimeError:
                return None, None, None, None

        if len(available_apis) == 1:
            choice = available_apis[0][0]
            logger.info(f"Using the only available API: {choice}")
        elif preferred_api and preferred_api in [api[0] for api in available_apis]:
            choice = preferred_api
            logger.info(f"Using preferred API: {choice}")
        else:
            choice = radiolist_dialog(
                title="Choose API",
                text="Multiple AI providers are available. Which one would you like to use?",
                values=available_apis
            ).run()

            if choice is None:
                logger.info("AI provider selection cancelled. Exiting program.")
                return None, None, None, None

        self.set_config_value("config", "PREFERRED_API", str(choice))

        if choice == "openai":
            logger.info(f"Using OpenAI API with model {openai_model}")
            return choice, openai_token, None, openai_model
        if choice == "anthropic":
            logger.info(f"Using Anthropic API with model {anthropic_model}")
            return choice, None, anthropic_token, anthropic_model

        # Ollama selected
        self.set_config_value("config", "OLLAMA_API_ENDPOINT", ollama_endpoint)
        self.set_config_value("config", "OLLAMA_MODEL", ollama_model)
        logger.info(f"Using Ollama with model {ollama_model} @ {ollama_endpoint}")
        return choice, None, None, ollama_model

    def select_openai_model(self, api_key):
        if not api_key or api_key == "NONE":
            logger.warning("No valid OpenAI API key available. Cannot select model.")
            return None

        try:
            client = OpenAI(api_key=api_key)
            models = client.models.list()
            
            model_choices = [(model.id, model.id) for model in models.data if "gpt" in model.id.lower()]
            
            selected_model = radiolist_dialog(
                title="Select OpenAI Model",
                text="Choose an OpenAI model from the list below:",
                values=model_choices
            ).run()
            
            if selected_model:
                self.set_config_value("config", "OPENAI_MODEL", selected_model)
                logger.info(f"Selected OpenAI model: {selected_model}")
                return selected_model
            else:
                logger.warning("No OpenAI model selected.")
                return None
        except Exception as e:
            logger.error(f"Error selecting OpenAI model: {str(e)}")
            return None

    def select_anthropic_model(self):
        self.models.extend([
            {"name": name, "model": model_id, "api_service": "anthropic"}
            for model_id, name in ANTHROPIC_MODELS
        ])
        
        selected_model = radiolist_dialog(
            title="Select Anthropic Model",
            text="Choose an Anthropic model from the list below:",
            values=ANTHROPIC_MODELS
        ).run()
        
        if selected_model:
            self.set_config_value("config", "ANTHROPIC_MODEL", selected_model)
            logger.info(f"Selected Anthropic model: {selected_model}")
            return selected_model
        else:
            logger.warning("No Anthropic model selected.")
            return None

    def select_gemini_model(self):
        self.models.extend([
            {"name": name, "model": model_id, "api_service": "gemini"}
            for model_id, name in GEMINI_MODELS
        ])

        selected_model = radiolist_dialog(
            title="Select Gemini Model",
            text="Choose a Gemini model from the list below:",
            values=GEMINI_MODELS
        ).run()
        
        if selected_model:
            self.set_config_value("config", "GEMINI_MODEL", selected_model)
            logger.info(f"Selected Gemini model: {selected_model}")
            return selected_model
        else:
            logger.warning("No Gemini model selected.")
            return None
        
    def setup_ssh_key(self):
        saved_ssh_key = self.get_config_value("config", "SSH_KEY")
        if saved_ssh_key and os.path.exists(saved_ssh_key):
            logger.info(f"Using saved SSH key: {saved_ssh_key}")
            self.configure_git_ssh(saved_ssh_key)
            return saved_ssh_key

        ssh_directory = os.path.expanduser("~/.ssh")
        if not os.path.exists(ssh_directory):
            logger.warning("No SSH keys found.")
            return None

        keys = [file for file in os.listdir(ssh_directory) if os.path.isfile(os.path.join(ssh_directory, file)) and not file.endswith(".pub")]
        if not keys:
            logger.warning("No SSH keys found.")
            return None

        logger.info("Available SSH keys:")
        for i, key in enumerate(keys, start=1):
            print(f"{i}. {key}")

        while True:
            try:
                choice = int(input("Enter the number of the SSH key to use: "))
                if 1 <= choice <= len(keys):
                    selected_key = keys[choice - 1]
                    break
                else:
                    logger.warning("Invalid choice. Please try again.")
            except ValueError:
                logger.warning("Invalid input. Please enter a valid number.")

        ssh_key_path = os.path.join(ssh_directory, selected_key)
        self.set_config_value("config", "SSH_KEY", ssh_key_path)
        logger.info(f"SSH key '{selected_key}' has been set up at '{ssh_key_path}'.")
        
        self.configure_git_ssh(ssh_key_path)
        return ssh_key_path

    def configure_git_ssh(self, ssh_key_path):
        ssh_config_path = os.path.expanduser('~/.ssh/config')
        git_host = 'github.com'

        config_entry = f"""
Host {git_host}
    IdentityFile {ssh_key_path}
    """

        if not os.path.exists(ssh_config_path):
            with open(ssh_config_path, 'w') as f:
                f.write(config_entry)
            logger.info(f"Created new SSH config file with Git configuration.")
        else:
            with open(ssh_config_path, 'r') as f:
                existing_config = f.read()

            if f"Host {git_host}" not in existing_config:
                with open(ssh_config_path, 'a') as f:
                    f.write(config_entry)
                logger.info(f"Added Git SSH configuration to existing SSH config file.")
            else:
                logger.info(f"Git SSH configuration already exists in SSH config file.")

        os.chmod(ssh_config_path, 0o600)
        logger.info(f"Git is now configured to use SSH key: {ssh_key_path}")

    def set_github_token(self, token):
        """
        Set and verify the GitHub API token.

        :param token: The GitHub API token to set
        :return: A tuple (success, message) indicating the result of the operation
        """
        try:
            # Verify the token before saving
            g = Github(token)
            g.get_user().login  # This will raise an exception if the token is invalid
            
            # Token is valid, save it
            self.set_config_value("config", "GITHUB_API_KEY", token)
            logger.info("GitHub API token set and verified successfully.")
            return True, "GitHub API token set and verified successfully."
        except Exception as e:
            error_message = f"Invalid GitHub API token: {str(e)}"
            logger.error(error_message)
            return False, error_message
        
    def get_github_token(self):
        try:
            github_token = self.get_config_value("config", "GITHUB_API_KEY")

            if github_token:
                # Initialize GitHub API client
                g = Github(github_token)
                g.get_user().login  # This will raise an exception if the token is invalid

                return {"token": github_token, "error": None}
            
        except Exception as e:
            error_message = f"Failed to load GitHub token from config: {e}"
            logger.error(error_message)

        try:
            github_token = os.environ.get("GITHUB_TOKEN")
        
            if github_token:
                # Initialize GitHub API client
                g = Github(github_token)
                g.get_user().login  # This will raise an exception if the token is invalid
            
                return {"token": github_token, "error": None}
            else:
                error_message = "GitHub token not found in environment."
        except Exception as e:
            error_message = f"Failed to load GitHub token from environment: {e}"
            logger.error(error_message)

        return {"token": None, "error": error_message}

    def clear_token_cache(self):
        self.check_openai_token.cache_clear()
        self.check_anthropic_token.cache_clear()
        self.check_gemini_token.cache_clear()
