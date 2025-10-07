import os
from typing import Dict
from dataclasses import dataclass, field

@dataclass
class ShellState:
    """Maintains shell session state"""
    cwd: str = field(default_factory=os.getcwd)
    env: Dict[str, str] = field(default_factory=lambda: dict(os.environ))
    mode: str = 'nl'  # Default to natural language mode
    last_exit_code: int = 0
    history: list = field(default_factory=list)
    aliases: Dict[str, str] = field(default_factory=dict)
    last_command: str = ''
    last_stdout: str = ''
    last_stderr: str = ''
    last_returncode: int = 0
    pending_commands: list = field(default_factory=list)
    prompt_prefill: str = ''

    def add_to_history(self, command: str):
        """Add command to history"""
        self.history.append(command)

    def get_prompt(self, username: str, api: str, model: str) -> str:
        """Generate shell prompt"""
        # Shorten cwd if in home directory
        display_cwd = self.cwd.replace(os.path.expanduser('~'), '~')

        mode_indicator = {
            'shell': '$',
            'nl': '$',
            'ai': '🤖 >'
        }.get(self.mode, '$')

        return f"{username}@{api}/{model} {display_cwd} {mode_indicator} "
