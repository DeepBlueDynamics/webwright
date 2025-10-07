import sys
import os
import platform
import shlex
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.history import FileHistory
from prompt_toolkit.formatted_text import FormattedText

from lib.config import Config
from lib.shell.state import ShellState
from lib.shell.executor import ShellExecutor, CommandResult
from lib.shell.parser import InputParser, InputType
from lib.shell.translator import NLTranslator
from lib.shell.input_buffer import InputBuffer
from lib.llm import llm_wrapper
from lib.util import custom_style, get_logger

# Setup logging
logger = get_logger()

# Ensure the .webwright directory exists
webwright_dir = os.path.expanduser('~/.webwright')
os.makedirs(webwright_dir, exist_ok=True)

class WebrightShell:
    """Main shell class - The Ghost in Your Shell"""

    def __init__(self, config: Config):
        self.config = config
        self.state = ShellState()
        self.executor = ShellExecutor(self.state)
        self.parser = InputParser()
        self.llm = llm_wrapper(config=config)
        self.translator = NLTranslator(self.llm)
        self.input_buffer = InputBuffer(self.state)
        self.agent_handle = 'webwright'
        self.prompt_username = ''
        self.prompt_api = ''
        self.prompt_model = ''

        # Setup history
        history_file = os.path.join(webwright_dir, 'webwright_history')
        self.history = FileHistory(history_file)
        self.session = PromptSession(history=self.history)

    async def run(self):
        """Main shell loop"""
        username = self.config.get_username()

        # Welcome message
        print_formatted_text(FormattedText([
            ('class:success', "Webwright Shell - The Ghost in Your Shell 👻\n"),
            ('', "Type "),
            ('class:inline-code', "'mode'"),
            ('', " to switch between shell/nl/ai modes, "),
            ('class:inline-code', "'exit'"),
            ('', " to quit\n")
        ]), style=custom_style)

        while True:
            try:
                # Reload config
                self.config.reload_config()

                # Get API/model info for prompt
                api = self.config.get_config_value("config", "PREFERRED_API")
                if api == "openai":
                    model = self.config.get_config_value("config", "OPENAI_MODEL")
                elif api == "anthropic":
                    model = self.config.get_config_value("config", "ANTHROPIC_MODEL")
                elif api == "ollama":
                    model = self.config.get_config_value("config", "OLLAMA_MODEL")
                else:
                    api = "unknown"
                    model = "unknown"

                self.prompt_username = username
                self.prompt_api = api
                self.prompt_model = model

                # Display prompt
                prompt = self.state.get_prompt(username, api, model)
                prompt_kwargs = {}
                if self.state.prompt_prefill:
                    prompt_kwargs['default'] = self.state.prompt_prefill
                user_input = await self.session.prompt_async(
                    FormattedText([('class:prompt', prompt)]),
                    style=custom_style,
                    **prompt_kwargs
                )
                # Clear prefill once consumed
                self.state.prompt_prefill = ''

                if not user_input.strip():
                    continue

                # Process input through input buffer (handles @files, {clipboard}, etc.)
                buffer_result = self.input_buffer.process_input(user_input)
                processed_input = buffer_result['command']
                file_context = buffer_result['context']

                # Classify input
                input_type = self.parser.classify(processed_input)

                # Handle based on type
                if input_type == InputType.EMPTY or input_type == InputType.COMMENT:
                    continue

                elif input_type == InputType.SHELL_COMMAND:
                    # Execute directly
                    result = self.executor.execute(processed_input)
                    self._print_result(result)
                    self.state.last_exit_code = result.returncode
                    pending_matched = False
                    if self.state.pending_commands and processed_input == self.state.pending_commands[0]:
                        self.state.pending_commands.pop(0)
                        pending_matched = True
                    if pending_matched and self.state.pending_commands:
                        await self._execute_translated_commands()

                elif input_type == InputType.NATURAL_LANGUAGE:
                    if await self._handle_shortcut(processed_input):
                        continue
                    # Translate to shell command
                    await self._handle_nl_translation(processed_input, file_context)

                elif input_type == InputType.AI_REQUEST:
                    # Enter AI assistant mode
                    request = self.parser.extract_ai_request(processed_input)
                    await self._handle_ai_mode(request, file_context)

                # Add to history
                self.state.add_to_history(user_input)

            except (KeyboardInterrupt, EOFError):
                print("\nUse 'exit' to quit")
            except SystemExit:
                print_formatted_text(FormattedText([
                    ('class:success', "\nGoodbye! 👻\n")
                ]), style=custom_style)
                break
            except Exception as e:
                print_formatted_text(FormattedText([
                    ('class:error', f"Error: {e}\n")
                ]), style=custom_style)
                logger.error(f"Error in shell loop: {e}", exc_info=True)

    async def _handle_nl_translation(self, nl_request: str, file_context: list):
        """Handle natural language translation and execution"""
        # Build context
        context = {
            'cwd': self.state.cwd,
            'recent_commands': self.state.history[-5:],
            'files_content': file_context,
            'last_command': self.state.last_command,
            'last_stdout': self.state.last_stdout[-2000:],
            'last_stderr': self.state.last_stderr[-2000:],
            'last_returncode': self.state.last_returncode,
            'os_name': os.name,
            'platform_system': platform.system(),
            'shell': os.getenv('SHELL') or os.getenv('ComSpec')
        }

        # Translate
        indicator_active = False
        try:
            self._show_translation_indicator()
            indicator_active = True

            command = await self.translator.translate(nl_request, context)
            self._clear_translation_indicator()
            indicator_active = False

            # Display translation with prompt-style formatting
            self._display_translation(command)

            actionable = [
                line.strip()
                for line in command.split('\n')
                if line.strip() and not line.strip().startswith('#')
            ]

            self.state.pending_commands = actionable.copy()
            await self._execute_translated_commands()

        except Exception as e:
            print_formatted_text(FormattedText([
                ('class:error', f"Translation error: {e}\n")
            ]), style=custom_style)
            logger.error(f"Translation error: {e}", exc_info=True)
        finally:
            if indicator_active:
                self._clear_translation_indicator()

    async def _handle_ai_mode(self, request: str, file_context: list):
        """Handle AI assistant mode (future: complex multi-step tasks)"""
        print_formatted_text(FormattedText([
            ('class:instruction', "AI mode not yet implemented - will support complex multi-step tasks\n"),
            ('', f"Request: {request}\n")
        ]), style=custom_style)

        # TODO: Implement AI assistant mode with function calling
        # This will bring back the power of the 30+ tools for complex tasks
        # See PLAN.md Phase 3 for implementation details

    def _display_translation(self, command: str):
        """Display translated command with shell-style prompt formatting"""
        # Get the mode indicator for the prompt
        for line in command.split('\n'):
            line_stripped = line.strip()
            if not line_stripped:
                continue

            if line_stripped.startswith('#'):
                print_formatted_text(FormattedText([
                    ('class:instruction', f"{line}\n")
                ]), style=custom_style)

    def _print_result(self, result: CommandResult, skip_command=False):
        """Print command result"""
        if result.stdout:
            print(result.stdout, end='')
        if result.stderr:
            print_formatted_text(FormattedText([
                ('class:error', result.stderr)
            ]), style=custom_style, end='')

    def _show_translation_indicator(self):
        """Show a transient LED-style indicator while translating."""
        indicator = '🔆 '
        sys.stdout.write(indicator)
        sys.stdout.flush()
        self._indicator_length = len(indicator)

    def _clear_translation_indicator(self):
        """Clear the translation indicator from the prompt."""
        length = getattr(self, '_indicator_length', 0)
        if length:
            sys.stdout.write('\r' + ' ' * length + '\r')
            sys.stdout.flush()
            self._indicator_length = 0

    def _print_agent_command(self, command: str, staged: bool = False):
        """Render a command as if the agent typed it at the prompt."""
        prompt_prefix = self._get_prompt_prefix()
        if staged:
            print_formatted_text(FormattedText([
                ('class:instruction', f"[{self.agent_handle} prepared command]\n")
            ]), style=custom_style)
        print_formatted_text(FormattedText([
            ('class:prompt', prompt_prefix),
            ('class:inline-code', f"{command}\n")
        ]), style=custom_style)

    def _get_prompt_prefix(self) -> str:
        """Compute a prompt string using the active shell context."""
        username = self.prompt_username
        return self.state.get_prompt(username, self.prompt_api, self.prompt_model)

    def _should_autorun(self, command: str) -> bool:
        """Determine whether a translated command should auto-run."""
        safe_prefixes = (
            'ls', 'pwd', 'cd', 'whoami', 'date', 'cat', 'echo',
            'git status', 'git diff', 'head', 'tail', 'dir'
        )
        risky_keywords = (
            'rm', 'mv', 'chmod', 'chown', 'docker', 'kubectl',
            'git push', 'git commit', 'pip install', 'npm install',
            'apt', 'brew', 'systemctl', 'shutdown', 'reboot'
        )

        command_lower = command.lower()

        if any(command_lower.startswith(prefix) for prefix in safe_prefixes):
            return True

        if any(keyword in command_lower for keyword in risky_keywords):
            return False

        # Auto-run simple script execution if the file exists locally
        if command_lower.startswith('python ') or command_lower.startswith('py '):
            try:
                parts = shlex.split(command)
            except ValueError:
                parts = command.split()

            if len(parts) >= 2:
                script_path = parts[1]
                if not os.path.isabs(script_path):
                    script_path = os.path.join(self.state.cwd, script_path)
                if os.path.isfile(script_path) and script_path.endswith('.py'):
                    return True

        return False

    async def _execute_translated_commands(self):
        """Execute commands currently staged in pending_commands."""
        for command in list(self.state.pending_commands):
            if self._should_autorun(command):
                self._print_agent_command(command)
                result = self.executor.execute(command)
                self._print_result(result, skip_command=True)
                self.state.last_exit_code = result.returncode
                self.state.pending_commands.remove(command)
            else:
                if not self.state.prompt_prefill:
                    self.state.prompt_prefill = command
                    self._print_agent_command(command, staged=True)
                    print_formatted_text(FormattedText([
                        ('class:instruction', "Press Enter to run or edit the prepared command."),
                        ('', "\n")
                    ]), style=custom_style)
                return

    async def _handle_shortcut(self, nl_request: str) -> bool:
        """Handle quick natural-language shortcuts before translation."""
        request = nl_request.strip().lower()

        rerun_phrases = {
            'run it', 'run that', 'execute it', 'do it', 'go ahead',
            'please run it', 'run the command', 'run those'
        }

        if request in rerun_phrases:
            await self._run_pending_commands()
            return True

        return False

    async def _run_pending_commands(self):
        """Execute any commands awaiting manual confirmation."""
        if not self.state.pending_commands:
            print_formatted_text(FormattedText([
                ('class:instruction', "Nothing queued to run.\n")
            ]), style=custom_style)
            return

        self.state.prompt_prefill = ''

        for command in list(self.state.pending_commands):
            self._print_agent_command(command)
            result = self.executor.execute(command)
            self._print_result(result, skip_command=True)
            self.state.last_exit_code = result.returncode
            self.state.pending_commands.remove(command)

def entry_point():
    """Entry point for webwright command"""
    # Show boot splash before slow imports/config
    from lib.boot import show_boot_splash
    show_boot_splash()

    config = Config()
    api_to_use, openai_token, anthropic_token, model_to_use = config.determine_api_to_use()

    if api_to_use is None:
        print("No AI provider selected. Exiting program.")
        sys.exit(1)

    if api_to_use == "openai" and not openai_token:
        print("Error: OpenAI selected but OPENAI_API_KEY is not configured.")
        sys.exit(1)

    if api_to_use == "anthropic" and not anthropic_token:
        print("Error: Anthropic selected but ANTHROPIC_API_KEY is not configured.")
        sys.exit(1)

    if api_to_use == "ollama":
        endpoint = config.get_config_value("config", "OLLAMA_API_ENDPOINT")
        if not endpoint:
            endpoint = "http://localhost:11434"
            config.set_config_value("config", "OLLAMA_API_ENDPOINT", endpoint)
        print(f"Using Ollama endpoint: {endpoint}")

    config.setup_ssh_key()

    # Clear the screen
    os.system('cls' if os.name == 'nt' else 'clear')

    # Create and run shell
    shell = WebrightShell(config)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(shell.run())
    except KeyboardInterrupt:
        print("\nShutdown complete.")
    finally:
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()

        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()

if __name__ == "__main__":
    entry_point()
