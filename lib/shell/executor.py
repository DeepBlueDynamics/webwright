import subprocess
import os
import shlex
from typing import Dict, Optional
from dataclasses import dataclass

@dataclass
class CommandResult:
    """Result from command execution"""
    returncode: int
    stdout: str
    stderr: str
    command: str

class ShellExecutor:
    """Executes shell commands deterministically"""

    def __init__(self, shell_state):
        self.state = shell_state
        self.builtins = self._register_builtins()

    def execute(self, command: str) -> CommandResult:
        """
        Execute a shell command with current state.

        :param command: Shell command to execute
        :return: CommandResult with output and status
        """
        command = command.strip()

        if not command or command.startswith('#'):
            return CommandResult(0, '', '', command)

        # Skip shell interpreter invocations (LLM sometimes outputs these)
        shell_interpreters = ['cmd', 'bash', 'sh', 'powershell', 'pwsh', 'zsh']
        if command.lower() in shell_interpreters:
            return CommandResult(0, '', '', command)

        # Check for built-in commands
        cmd_parts = shlex.split(command) if command else []
        if cmd_parts and cmd_parts[0] in self.builtins:
            result = self.builtins[cmd_parts[0]](cmd_parts[1:])
            self._record_result(result)
            return result

        # Execute external command
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.state.cwd,
                env=self.state.env,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            result = CommandResult(
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                command=command
            )
            self._record_result(result)
            return result

        except subprocess.TimeoutExpired:
            result = CommandResult(
                returncode=124,
                stdout='',
                stderr='Command timed out after 5 minutes',
                command=command
            )
            self._record_result(result)
            return result
        except Exception as e:
            result = CommandResult(
                returncode=1,
                stdout='',
                stderr=f'Execution error: {str(e)}',
                command=command
            )
            self._record_result(result)
            return result

    def _register_builtins(self) -> Dict:
        """Register built-in commands"""
        return {
            'cd': self._builtin_cd,
            'export': self._builtin_export,
            'pwd': self._builtin_pwd,
            'exit': self._builtin_exit,
            'mode': self._builtin_mode,
        }

    def _builtin_cd(self, args: list) -> CommandResult:
        """Change directory built-in"""
        target = args[0] if args else os.path.expanduser('~')
        target = os.path.expanduser(target)

        if not os.path.isabs(target):
            target = os.path.join(self.state.cwd, target)

        target = os.path.normpath(target)

        if os.path.isdir(target):
            self.state.cwd = target
            os.chdir(target)
            return CommandResult(0, '', '', f'cd {args[0] if args else "~"}')
        else:
            return CommandResult(
                1, '', f'cd: {target}: No such directory\n',
                f'cd {args[0] if args else "~"}'
            )

    def _builtin_pwd(self, args: list) -> CommandResult:
        """Print working directory"""
        return CommandResult(0, self.state.cwd + '\n', '', 'pwd')

    def _builtin_export(self, args: list) -> CommandResult:
        """Export environment variable"""
        if not args:
            # Print all env vars
            output = '\n'.join(f'{k}={v}' for k, v in self.state.env.items())
            return CommandResult(0, output + '\n', '', 'export')

        for arg in args:
            if '=' in arg:
                key, value = arg.split('=', 1)
                self.state.env[key] = value
                os.environ[key] = value

        return CommandResult(0, '', '', f'export {" ".join(args)}')

    def _builtin_exit(self, args: list) -> CommandResult:
        """Exit the shell"""
        code = int(args[0]) if args and args[0].isdigit() else 0
        raise SystemExit(code)

    def _builtin_mode(self, args: list) -> CommandResult:
        """Switch between shell/NL/AI modes"""
        if not args:
            current = self.state.mode
            return CommandResult(
                0,
                f'Current mode: {current}\nAvailable: shell, nl, ai\n',
                '',
                'mode'
            )

        mode = args[0].lower()
        if mode in ['shell', 'nl', 'ai']:
            self.state.mode = mode
            return CommandResult(0, f'Switched to {mode} mode\n', '', f'mode {mode}')
        else:
            return CommandResult(
                1, '',
                f'Invalid mode: {mode}. Use: shell, nl, or ai\n',
                f'mode {mode}'
            )

    def _record_result(self, result: CommandResult) -> None:
        """Persist command execution details on shell state"""
        self.state.last_command = result.command
        self.state.last_stdout = result.stdout
        self.state.last_stderr = result.stderr
        self.state.last_returncode = result.returncode
