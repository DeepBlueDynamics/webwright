import os
import re
from enum import Enum
from typing import Tuple

class InputType(Enum):
    SHELL_COMMAND = "shell"
    NATURAL_LANGUAGE = "nl"
    AI_REQUEST = "ai"
    COMMENT = "comment"
    EMPTY = "empty"

class InputParser:
    """Classifies and parses user input"""

    # Common shell command patterns
    SHELL_COMMANDS = {
        'ls', 'cd', 'pwd', 'cat', 'echo', 'grep', 'find', 'git',
        'python', 'node', 'npm', 'pip', 'docker', 'kubectl',
        'mkdir', 'rm', 'cp', 'mv', 'touch', 'chmod', 'chown',
        'ps', 'kill', 'top', 'df', 'du', 'tar', 'gzip', 'curl', 'wget',
        'export', 'mode'
    }

    if os.name == 'nt':
        SHELL_COMMANDS.update({'dir', 'type', 'cls', 'copy', 'del'})

    # AI mode trigger
    AI_PREFIX = 'ai:'

    def classify(self, user_input: str) -> InputType:
        """
        Classify user input type.

        :param user_input: Raw user input string
        :return: InputType classification
        """
        stripped = user_input.strip()

        # Empty or comment
        if not stripped:
            return InputType.EMPTY
        if stripped.startswith('#'):
            return InputType.COMMENT

        # Explicit AI mode
        if stripped.lower().startswith(self.AI_PREFIX):
            return InputType.AI_REQUEST

        # Shell command indicators
        if self._is_shell_command(stripped):
            return InputType.SHELL_COMMAND

        # Default to natural language
        return InputType.NATURAL_LANGUAGE

    def _is_shell_command(self, text: str) -> bool:
        """Determine if text is a shell command"""
        # Starts with known command
        first_word = text.split()[0] if text.split() else ''
        if first_word in self.SHELL_COMMANDS:
            return True

        # Contains shell operators
        shell_operators = ['|', '>', '<', '&&', '||', ';', '>>']
        if any(op in text for op in shell_operators):
            return True

        # Looks like a path
        if first_word.startswith('./') or first_word.startswith('/'):
            return True

        # Environment variable assignment
        if '=' in first_word and ' ' not in first_word:
            return True

        return False

    def extract_ai_request(self, user_input: str) -> str:
        """Extract AI request from 'ai: <request>' format"""
        if user_input.strip().lower().startswith(self.AI_PREFIX):
            return user_input.strip()[len(self.AI_PREFIX):].strip()
        return user_input
