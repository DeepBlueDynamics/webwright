# Webwright Shell Refactoring Plan

## Vision

Transform Webwright from an AI-powered conversational assistant into a **true shell** that understands natural language. The core principle: **everything executes deterministically through standard shell commands**, with the LLM serving as a natural language → shell command translator.

### Design Philosophy

```bash
user@webwright ~/project $ show me the git status

# Checking current git repository status
git status

On branch main
Your branch is up to date with 'origin/main'.

user@webwright ~/project $ commit these changes with message "update docs"

# Staging all modified files and creating commit
git add -u
git commit -m "update docs"

[main a1b2c3d] update docs
 2 files changed, 45 insertions(+)
```

**Key Principles:**
1. Natural language input → Shell command output
2. Comments explain what's happening (valid shell syntax)
3. Actual commands execute deterministically (no LLM in execution path)
4. Full shell compatibility (pipes, redirects, job control)
5. Transparent and copy/paste friendly

---

## Current Architecture Analysis

### Current Components

```
webwright/
├── main.py                 # Entry point, prompt loop
├── lib/
│   ├── aifunc.py          # AI function orchestration
│   ├── llm.py             # Multi-provider LLM wrapper
│   ├── omnilog.py         # Vector store for conversation history
│   ├── function_wrapper.py # Tool registration system
│   ├── config.py          # Configuration management
│   └── functions/         # 30+ tool implementations
│       ├── git_*.py       # Git operations
│       ├── filesystem.py  # File operations
│       ├── browser.py     # Browser automation
│       └── ...
```

### Current Flow

```
User Input → LLM (with tools) → Function Calls → Execution → LLM Summary → Output
```

### Problems with Current Approach

1. **Not a shell**: Can't use pipes, redirects, or standard shell features
2. **LLM in execution path**: Non-deterministic, slower, expensive
3. **Black box execution**: User can't see what commands run
4. **Conversation-based**: Not command-line oriented
5. **No shell compatibility**: Can't run shell scripts or use with existing tools
6. **Limited composability**: Can't chain operations with standard Unix tools

---

## Target Architecture

### New Components

```
webwright/
├── main.py                      # Shell REPL with NL support
├── lib/
│   ├── shell/
│   │   ├── executor.py         # Command execution engine
│   │   ├── parser.py           # Input classification & parsing
│   │   ├── translator.py       # NL → Shell command translation
│   │   ├── state.py            # Shell state management (cwd, env, etc.)
│   │   ├── builtin.py          # Built-in commands (cd, export, etc.)
│   │   ├── completion.py       # Tab completion
│   │   └── input_buffer.py     # Multi-line paste, file refs, clipboard
│   ├── ai/
│   │   ├── mode_manager.py     # Switch between shell/AI/hybrid modes
│   │   ├── translator_llm.py   # LLM for NL translation
│   │   ├── assistant.py        # Complex multi-step AI tasks
│   │   └── context.py          # Conversation context management
│   ├── llm.py                  # Keep existing multi-provider LLM
│   ├── omnilog.py              # Keep for AI mode context
│   ├── config.py               # Enhanced configuration
│   └── legacy/
│       └── functions/          # Migrate to hybrid AI mode
```

### New Flow

```
User Input
    ↓
Input Classifier
    ↓
    ├─→ Shell Command? ──→ Executor ──→ Output
    │
    └─→ Natural Language?
            ↓
        NL Translator (LLM)
            ↓
        Generate: Comment + Shell Command(s)
            ↓
        Display Translation
            ↓
        Executor ──→ Output
            ↓
        (Optional) Update Context
```

### Mode System

**Three Operating Modes:**

1. **Shell Mode** (default): Direct command execution
   ```bash
   $ ls -la | grep py
   $ git status
   $ echo "hello" > file.txt
   ```

2. **NL Mode**: Natural language → shell translation
   ```bash
   $ show me all python files
   # Listing all Python files in current directory
   ls -la | grep py

   $ commit these changes
   # Staging and committing all modified files
   git add -u && git commit
   ```

3. **AI Assistant Mode**: Complex multi-step tasks with planning
   ```bash
   $ ai: analyze this codebase and suggest improvements
   [Enters AI mode with function calling, planning, code analysis]

   $ ai: create a new feature with tests and documentation
   [Multi-step planning with user confirmation]
   ```

### Input Buffer System - The Paste Problem Solution

**The Challenge:** How do you give the AI context (code, files, data) in a shell environment without losing the slick paste UX of chat interfaces?

**The Solution:** Multiple input methods that feel natural in a shell:

#### 1. File References (@syntax)
```bash
$ ai: analyze @src/main.py @lib/util.py
# Agent automatically reads files

$ show me @README.md
# Works in NL mode too

$ ai: compare @original.py with @modified.py

$ ai: review @**/*.py
# Glob support for multiple files
```

#### 2. Clipboard Integration ({clipboard})
```bash
$ ai: analyze {clipboard}
# Reads from system clipboard

$ ai: review {clip}
# Shorthand version

$ ai: compare @file.py with {clipboard}
# Mix file refs and clipboard
```

#### 3. Heredoc (standard shell)
```bash
$ ai: analyze << CODE
def complex_function():
    return 42
CODE

$ ai: explain << EOF
Multi-line content
Can paste anything here
EOF
```

#### 4. Pipe (Unix way)
```bash
$ cat file.py | ai: analyze
$ git diff | ai: review these changes
$ curl https://api.example.com | ai: explain this
$ docker logs myapp | ai: find errors
```

#### 5. Auto-detect Bracketed Paste
```bash
$ ai: analyze
> [Terminal detects large paste, auto-enters multi-line mode]
> [Paste your code]
> [Ctrl+D to end]
```

**Implementation Priority:** File references (@) and pipes first, then clipboard, then heredoc.

---

## Implementation Plan

### Phase 1: Core Shell Infrastructure (Week 1-2)

#### 1.1 Command Executor

**File:** `lib/shell/executor.py`

```python
import subprocess
import os
import shlex
from typing import Dict, Optional, Tuple
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

        # Check for built-in commands
        cmd_parts = shlex.split(command)
        if cmd_parts and cmd_parts[0] in self.builtins:
            return self.builtins[cmd_parts[0]](cmd_parts[1:])

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

            return CommandResult(
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                command=command
            )

        except subprocess.TimeoutExpired:
            return CommandResult(
                returncode=124,
                stdout='',
                stderr='Command timed out after 5 minutes',
                command=command
            )
        except Exception as e:
            return CommandResult(
                returncode=1,
                stdout='',
                stderr=f'Execution error: {str(e)}',
                command=command
            )

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
                1, '', f'cd: {target}: No such directory',
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
            return CommandResult(0, output, '', 'export')

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
```

#### 1.2 Shell State Management

**File:** `lib/shell/state.py`

```python
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
            'ai': '🤖'
        }.get(self.mode, '$')

        return f"{username}@{api}/{model} {display_cwd} {mode_indicator} "
```

#### 1.3 Input Parser/Classifier

**File:** `lib/shell/parser.py`

```python
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
        'ps', 'kill', 'top', 'df', 'du', 'tar', 'gzip', 'curl', 'wget'
    }

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
```

#### 1.4 Natural Language Translator

**File:** `lib/shell/translator.py`

```python
from typing import List, Tuple
from lib.llm import llm_wrapper

class NLTranslator:
    """Translates natural language to shell commands using LLM"""

    TRANSLATION_PROMPT = """You are a shell command translator. Convert natural language requests into shell commands.

Rules:
1. Output ONLY shell commands and comments (valid shell syntax)
2. Use comments (starting with #) to explain what you're doing
3. Generate actual executable commands that will run deterministically
4. Use standard Unix/Linux commands
5. Be concise - prefer single commands over complex scripts
6. If the request is ambiguous, make reasonable assumptions
7. For destructive operations, add a comment warning

Examples:

Input: "show me all python files"
Output:
# Listing all Python files in current directory
ls *.py

Input: "what's the git status"
Output:
# Checking git repository status
git status

Input: "find large files over 100MB"
Output:
# Finding files larger than 100MB in current directory
find . -type f -size +100M

Input: "commit these changes with message fix bug"
Output:
# Staging all changes and committing
git add -A
git commit -m "fix bug"

Now translate this request:"""

    def __init__(self, llm: llm_wrapper):
        self.llm = llm

    async def translate(self, nl_request: str, context: dict = None) -> str:
        """
        Translate natural language to shell command(s).

        :param nl_request: Natural language request
        :param context: Optional context (cwd, recent commands, etc.)
        :return: Shell command(s) with comments
        """
        # Build context-aware prompt
        prompt = self.TRANSLATION_PROMPT

        if context:
            if 'cwd' in context:
                prompt += f"\n\nCurrent directory: {context['cwd']}"
            if 'recent_commands' in context:
                prompt += f"\n\nRecent commands:\n" + "\n".join(context['recent_commands'][-3:])

        prompt += f"\n\nUser request: {nl_request}"

        messages = [{"type": "user_query", "content": prompt, "timestamp": ""}]

        # Call LLM without tools (just text generation)
        response = await self.llm.call_llm_api(
            messages=messages,
            system_prompt="You are a shell command translator. Output only shell commands and comments.",
            tools=None
        )

        command = response.get('content', '').strip()

        # Clean up any markdown code blocks
        command = self._clean_output(command)

        return command

    def _clean_output(self, text: str) -> str:
        """Clean LLM output to extract shell commands"""
        # Remove markdown code blocks
        if '```' in text:
            parts = text.split('```')
            for part in parts:
                if part.strip().startswith('bash') or part.strip().startswith('sh'):
                    text = part.replace('bash', '').replace('sh', '').strip()
                    break
            else:
                # Take first code block
                text = parts[1] if len(parts) > 1 else text

        return text.strip()
```

#### 1.4a Input Buffer - Context Handler

**File:** `lib/shell/input_buffer.py`

```python
import os
import sys
import re
import glob as globlib
from typing import List, Dict, Tuple

class InputBuffer:
    """
    Handle different input methods for pasting/file references.
    Solves the "paste problem" - how to give context to AI in a shell.
    """

    def __init__(self, shell_state):
        self.state = shell_state

    def process_input(self, text: str) -> Dict:
        """
        Parse input and extract content from various sources.

        Supports:
        - File references: @file.py, @**/*.py
        - Clipboard: {clipboard}, {clip}
        - Stdin pipe: cat file | command

        :param text: User input text
        :return: {
            'command': str,        # Cleaned command text
            'context': List[str],  # Additional context from files/paste
            'files': List[str]     # File paths referenced
        }
        """
        context = []
        files = []

        # 1. Check for stdin pipe
        if not sys.stdin.isatty():
            stdin_content = sys.stdin.read()
            if stdin_content:
                context.append(f"# Stdin:\n{stdin_content}")

        # 2. File references (@file.py or @**/*.py)
        file_refs = re.findall(r'@([^\s]+)', text)
        for ref in file_refs:
            if '*' in ref:
                # Glob pattern
                matched_files = globlib.glob(ref, recursive=True)
                for f in matched_files:
                    content = self._read_file(f)
                    if content:
                        context.append(content)
                        files.append(f)
            else:
                # Single file
                content = self._read_file(ref)
                if content:
                    context.append(content)
                    files.append(ref)

        # 3. Clipboard reference ({clipboard}, {clip})
        if '{clipboard}' in text or '{clip}' in text:
            clipboard_content = self._get_clipboard()
            if clipboard_content:
                context.append(f"# Clipboard:\n{clipboard_content}")

        # 4. Clean command (remove @ refs and clipboard markers)
        clean_command = text
        for ref in file_refs:
            clean_command = clean_command.replace(f'@{ref}', '')
        clean_command = clean_command.replace('{clipboard}', '').replace('{clip}', '')
        clean_command = clean_command.strip()

        return {
            'command': clean_command,
            'context': context,
            'files': files
        }

    def _read_file(self, path: str) -> str:
        """
        Read file and return with metadata.

        :param path: File path (relative or absolute)
        :return: File content with header, or empty string on error
        """
        try:
            # Resolve relative paths
            if not os.path.isabs(path):
                path = os.path.join(self.state.cwd, path)

            # Check file exists
            if not os.path.isfile(path):
                return f"# Error: File not found: {path}\n"

            # Read file
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # Return with metadata header
            rel_path = os.path.relpath(path, self.state.cwd)
            return f"# File: {rel_path}\n{content}\n"

        except Exception as e:
            return f"# Error reading {path}: {str(e)}\n"

    def _get_clipboard(self) -> str:
        """
        Get clipboard content (cross-platform).

        :return: Clipboard text or empty string
        """
        try:
            # Try pyperclip first (cross-platform)
            import pyperclip
            return pyperclip.paste()
        except ImportError:
            # Fallback to platform-specific commands
            import subprocess

            try:
                if sys.platform == 'darwin':
                    # macOS
                    return subprocess.check_output(['pbpaste']).decode('utf-8')
                elif sys.platform == 'linux':
                    # Linux (requires xclip)
                    return subprocess.check_output(['xclip', '-selection', 'clipboard', '-o']).decode('utf-8')
                elif sys.platform == 'win32':
                    # Windows
                    import win32clipboard
                    win32clipboard.OpenClipboard()
                    data = win32clipboard.GetClipboardData()
                    win32clipboard.CloseClipboard()
                    return data
            except Exception:
                pass

        return ""

    def extract_heredoc(self, session) -> str:
        """
        Handle heredoc input (multi-line).

        Example:
            $ ai: analyze << EOF
            def foo():
                pass
            EOF

        :param session: PromptSession for reading additional lines
        :return: Heredoc content
        """
        lines = []
        delimiter = None

        # TODO: Implement heredoc parsing
        # For now, return empty
        return ""
```

#### 1.5 Main Shell Loop

**File:** `main.py` (refactored)

```python
import sys
import os
import asyncio
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.formatted_text import FormattedText

from lib.config import Config
from lib.shell.state import ShellState
from lib.shell.executor import ShellExecutor
from lib.shell.parser import InputParser, InputType
from lib.shell.translator import NLTranslator
from lib.llm import llm_wrapper
from lib.util import custom_style

class WebrightShell:
    """Main shell class"""

    def __init__(self, config: Config):
        self.config = config
        self.state = ShellState()
        self.executor = ShellExecutor(self.state)
        self.parser = InputParser()
        self.llm = llm_wrapper(config=config)
        self.translator = NLTranslator(self.llm)

        # Setup history
        webwright_dir = os.path.expanduser('~/.webwright')
        os.makedirs(webwright_dir, exist_ok=True)
        history_file = os.path.join(webwright_dir, 'webwright_history')
        self.history = FileHistory(history_file)
        self.session = PromptSession(history=self.history)

    async def run(self):
        """Main shell loop"""
        username = self.config.get_username()

        print("Webwright Shell - The Ghost in Your Shell 👻")
        print("Type 'mode' to switch between shell/nl/ai modes, 'exit' to quit\n")

        while True:
            try:
                # Get API/model info for prompt
                api = self.config.get_config_value("config", "PREFERRED_API")
                if api == "openai":
                    model = self.config.get_config_value("config", "OPENAI_MODEL")
                elif api == "anthropic":
                    model = self.config.get_config_value("config", "ANTHROPIC_MODEL")
                else:
                    model = "unknown"

                # Display prompt
                prompt = self.state.get_prompt(username, api, model)
                user_input = await self.session.prompt_async(
                    FormattedText([('class:prompt', prompt)]),
                    style=custom_style
                )

                if not user_input.strip():
                    continue

                # Classify input
                input_type = self.parser.classify(user_input)

                # Handle based on type
                if input_type == InputType.EMPTY or input_type == InputType.COMMENT:
                    continue

                elif input_type == InputType.SHELL_COMMAND:
                    # Execute directly
                    result = self.executor.execute(user_input)
                    self._print_result(result)
                    self.state.last_exit_code = result.returncode

                elif input_type == InputType.NATURAL_LANGUAGE:
                    # Translate to shell command
                    await self._handle_nl_translation(user_input)

                elif input_type == InputType.AI_REQUEST:
                    # Enter AI assistant mode
                    request = self.parser.extract_ai_request(user_input)
                    await self._handle_ai_mode(request)

                # Add to history
                self.state.add_to_history(user_input)

            except (KeyboardInterrupt, EOFError):
                print("\nUse 'exit' to quit")
            except SystemExit:
                print("\nGoodbye! 👻")
                break
            except Exception as e:
                print(f"Error: {e}")

    async def _handle_nl_translation(self, nl_request: str):
        """Handle natural language translation and execution"""
        # Build context
        context = {
            'cwd': self.state.cwd,
            'recent_commands': self.state.history[-5:]
        }

        # Translate
        print("Translating...")
        command = await self.translator.translate(nl_request, context)

        # Display translation
        print(command)

        # Execute each line
        for line in command.split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                result = self.executor.execute(line)
                self._print_result(result, skip_command=True)
                self.state.last_exit_code = result.returncode

    async def _handle_ai_mode(self, request: str):
        """Handle AI assistant mode (future: complex multi-step tasks)"""
        print("AI mode not yet implemented - will support complex multi-step tasks")
        print(f"Request: {request}")

    def _print_result(self, result, skip_command=False):
        """Print command result"""
        if result.stdout:
            print(result.stdout, end='')
        if result.stderr:
            print(result.stderr, end='', file=sys.stderr)

def entry_point():
    """Entry point for webwright command"""
    config = Config()
    shell = WebrightShell(config)

    # Run the shell
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(shell.run())
    finally:
        loop.close()

if __name__ == "__main__":
    entry_point()
```

---

### Phase 2: Enhanced Shell Features (Week 3-4)

#### 2.1 Tab Completion

**File:** `lib/shell/completion.py`

```python
from prompt_toolkit.completion import Completer, Completion
import os

class ShellCompleter(Completer):
    """Tab completion for commands, files, and paths"""

    def __init__(self, shell_state):
        self.state = shell_state
        self.commands = self._get_commands()

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        words = text.split()

        if not words:
            # Complete commands
            for cmd in self.commands:
                yield Completion(cmd, start_position=0)
        elif len(words) == 1:
            # Complete command or file
            prefix = words[0]
            for cmd in self.commands:
                if cmd.startswith(prefix):
                    yield Completion(cmd, start_position=-len(prefix))

            # File/directory completion
            yield from self._complete_path(prefix)
        else:
            # Complete file/directory arguments
            prefix = words[-1]
            yield from self._complete_path(prefix)

    def _complete_path(self, prefix):
        """Complete file/directory paths"""
        directory = os.path.dirname(prefix) or '.'
        basename = os.path.basename(prefix)

        try:
            for item in os.listdir(directory):
                if item.startswith(basename):
                    full_path = os.path.join(directory, item)
                    if os.path.isdir(full_path):
                        yield Completion(item + '/', start_position=-len(basename))
                    else:
                        yield Completion(item, start_position=-len(basename))
        except (OSError, PermissionError):
            pass

    def _get_commands(self):
        """Get list of available commands from PATH"""
        commands = set()
        for path in os.environ.get('PATH', '').split(os.pathsep):
            try:
                for item in os.listdir(path):
                    if os.access(os.path.join(path, item), os.X_OK):
                        commands.add(item)
            except (OSError, PermissionError):
                pass
        return sorted(commands)
```

#### 2.2 Advanced Parsing (Pipes, Redirects)

**File:** `lib/shell/advanced_executor.py`

```python
import subprocess
import shlex
from typing import List

class AdvancedExecutor:
    """Handle pipes, redirects, and command chaining"""

    def __init__(self, shell_state):
        self.state = shell_state

    def execute_pipeline(self, command: str):
        """Execute command with pipes"""
        if '|' not in command:
            return self._execute_simple(command)

        commands = [cmd.strip() for cmd in command.split('|')]
        processes = []

        for i, cmd in enumerate(commands):
            stdin = processes[-1].stdout if processes else None
            stdout = subprocess.PIPE if i < len(commands) - 1 else None

            proc = subprocess.Popen(
                cmd,
                shell=True,
                stdin=stdin,
                stdout=stdout,
                stderr=subprocess.PIPE,
                cwd=self.state.cwd,
                env=self.state.env
            )
            processes.append(proc)

        # Get output from last process
        stdout, stderr = processes[-1].communicate()
        returncode = processes[-1].returncode

        return CommandResult(
            returncode=returncode,
            stdout=stdout.decode() if stdout else '',
            stderr=stderr.decode() if stderr else '',
            command=command
        )
```

---

### Phase 3: Hybrid AI Mode (Week 5-6)

#### 3.1 AI Assistant Mode

**File:** `lib/ai/assistant.py`

```python
from lib.omnilog import OmniLogVectorStore
from lib.function_wrapper import tools, callable_registry
from lib.aifunc import execute_function_by_name

class AIAssistant:
    """
    Complex multi-step AI assistant mode.
    Uses existing function calling infrastructure for complex tasks.
    """

    def __init__(self, llm, omnilog: OmniLogVectorStore):
        self.llm = llm
        self.omnilog = omnilog

    async def handle_request(self, request: str):
        """
        Handle complex AI requests with function calling.

        Example:
            ai: analyze this codebase and create a performance report
            ai: set up a new React project with TypeScript and tests
        """
        # Add request to omnilog
        self.omnilog.add_entry({
            'content': request,
            'type': 'user_query',
            'timestamp': datetime.now().isoformat()
        })

        # Use existing AI function calling infrastructure
        # This brings back the power of the 30+ tools for complex tasks
        messages = self.omnilog.get_recent_entries(10)

        response = await self.llm.call_llm_api(
            messages=messages,
            system_prompt=self._get_assistant_prompt(),
            tools=tools
        )

        # Handle function calls if any
        if response.get('function_calls'):
            for func_call in response['function_calls']:
                result = await execute_function_by_name(
                    func_call['name'],
                    self.llm,
                    self.omnilog,
                    **func_call['arguments']
                )
                print(f"Executed: {func_call['name']}")
                print(result)

        # Display response
        if response.get('content'):
            print(response['content'])

    def _get_assistant_prompt(self):
        """System prompt for AI assistant mode"""
        return """You are Webwright AI Assistant. You help with complex, multi-step development tasks.

You have access to powerful functions for:
- Code analysis and generation
- Git operations
- File system manipulation
- GitHub integration
- Docker management
- Web search and browsing

For complex tasks:
1. Break down into steps
2. Ask for confirmation before destructive operations
3. Use function calls to accomplish tasks
4. Provide clear status updates

For simple shell tasks, suggest the user use natural language mode instead.
"""
```

#### 3.2 Mode Manager

**File:** `lib/ai/mode_manager.py`

```python
from enum import Enum

class ShellMode(Enum):
    SHELL = "shell"      # Direct shell command execution
    NL = "nl"           # Natural language → shell translation
    AI = "ai"           # AI assistant with function calling

class ModeManager:
    """Manages switching between shell modes"""

    def __init__(self, state):
        self.state = state

    def switch_mode(self, mode: str):
        """Switch shell mode"""
        if mode.lower() in [m.value for m in ShellMode]:
            self.state.mode = mode.lower()
            return True
        return False

    def get_mode_description(self, mode: str) -> str:
        """Get description for a mode"""
        descriptions = {
            'shell': 'Direct shell command execution (like bash)',
            'nl': 'Natural language → shell command translation (default)',
            'ai': 'AI assistant for complex multi-step tasks'
        }
        return descriptions.get(mode, 'Unknown mode')
```

---

### Phase 4: Advanced Features (Week 7-8)

#### 4.1 Smart History Search

```python
class SmartHistory:
    """Intelligent command history with NL search"""

    def search_nl(self, query: str) -> List[str]:
        """Search history with natural language"""
        # Use vector search on command history
        pass
```

#### 4.2 Command Suggestions

```python
class CommandSuggester:
    """Suggest commands based on context"""

    def suggest(self, partial_input: str, context: dict) -> List[str]:
        """Suggest completions using LLM"""
        pass
```

#### 4.3 Alias Learning

```python
class AliasLearner:
    """Learn user patterns and suggest aliases"""

    def analyze_patterns(self):
        """Find repeated command patterns"""
        pass

    def suggest_alias(self, pattern: str) -> str:
        """Suggest an alias for a pattern"""
        pass
```

---

## Migration Strategy

### Backward Compatibility

Keep existing functionality available through AI mode:

```python
# lib/legacy/function_bridge.py
"""
Bridge to maintain compatibility with existing function-based tools.
All 30+ functions remain available in AI assistant mode.
"""

class FunctionBridge:
    """Makes old functions available in new architecture"""

    # All existing functions accessible via 'ai:' mode
    # Example: ai: create a github repo called "my-project"
```

### Gradual Migration Path

1. **Phase 1**: Launch new shell mode alongside existing mode
2. **Phase 2**: Make new shell the default
3. **Phase 3**: Move complex functions to AI mode
4. **Phase 4**: Deprecate old conversational interface

---

## Testing Strategy

### Unit Tests

```python
# tests/test_translator.py
async def test_nl_translation():
    translator = NLTranslator(mock_llm)
    result = await translator.translate("show me python files")
    assert "ls" in result
    assert "*.py" in result

# tests/test_executor.py
def test_command_execution():
    executor = ShellExecutor(mock_state)
    result = executor.execute("echo hello")
    assert result.stdout == "hello\n"
    assert result.returncode == 0

# tests/test_parser.py
def test_input_classification():
    parser = InputParser()
    assert parser.classify("ls -la") == InputType.SHELL_COMMAND
    assert parser.classify("show me files") == InputType.NATURAL_LANGUAGE
    assert parser.classify("ai: analyze code") == InputType.AI_REQUEST
```

### Integration Tests

```python
# tests/test_shell_integration.py
async def test_nl_to_execution():
    shell = WebrightShell(config)
    await shell.process_input("show me all python files")
    # Verify translation happened
    # Verify command executed
    # Verify output displayed
```

### Manual Test Cases

```bash
# Test natural language translation
$ show me the git status
$ find all python files
$ what files changed recently

# Test shell commands
$ ls -la | grep py
$ git status
$ echo "hello" > test.txt

# Test AI mode
$ ai: analyze this codebase and suggest improvements
$ ai: create a new feature with tests

# Test mode switching
$ mode shell
$ mode nl
$ mode ai
$ mode
```

---

## Success Criteria

### Core Functionality
- ✅ Direct shell command execution works
- ✅ Natural language translates to valid shell commands
- ✅ Comments explain what commands do
- ✅ All commands execute deterministically
- ✅ Shell state (cwd, env) maintained correctly
- ✅ Pipes and redirects work
- ✅ Mode switching works smoothly

### User Experience
- ✅ Transparent: users see what commands run
- ✅ Fast: NL translation < 2 seconds
- ✅ Accurate: 90%+ correct translations
- ✅ Copy/paste friendly: output is valid shell
- ✅ Shell-compatible: works with existing tools

### Technical
- ✅ No LLM in execution path
- ✅ Existing tools accessible in AI mode
- ✅ Backward compatible
- ✅ Well tested (80%+ coverage)
- ✅ Documented

---

## Example Usage Scenarios

### Scenario 1: Daily Development

```bash
user@anthropic/claude ~/project $ what changed in git

# Showing git status and recent changes
git status
git diff

On branch main
Changes not staged for commit:
  modified:   lib/shell/executor.py
  modified:   README.md

user@anthropic/claude ~/project $ commit these with message "add executor"

# Staging all changes and creating commit
git add -A
git commit -m "add executor"

[main f4a5b6c] add executor
 2 files changed, 120 insertions(+)

user@anthropic/claude ~/project $ push to github

# Pushing commits to remote repository
git push origin main

Enumerating objects: 8, done.
Counting objects: 100% (8/8), done.
```

### Scenario 2: File Operations

```bash
user@anthropic/claude ~/project $ show me all files over 1MB

# Finding files larger than 1MB
find . -type f -size +1M -ls

user@anthropic/claude ~/project $ create a backup of the lib folder

# Creating compressed backup of lib directory
tar -czf lib_backup_$(date +%Y%m%d).tar.gz lib

lib_backup_20241006.tar.gz created
```

### Scenario 3: Complex AI Task

```bash
user@anthropic/claude ~/project $ ai: analyze this Python project and create a test coverage report

[Entering AI Assistant mode]

I'll analyze your Python project and generate a test coverage report. This will involve:

1. Scanning Python files in the project
2. Running pytest with coverage
3. Generating a detailed report

Shall I proceed?

user@anthropic/claude ~/project $ yes

Executing: scan_python_code
Found 24 Python files, 3,450 lines of code

Executing: run_python_file (pytest with coverage)
Coverage: 67%

Generated report:
- Total files: 24
- Total lines: 3,450
- Test coverage: 67%
- Files without tests: lib/shell/translator.py, lib/ai/assistant.py

Recommendation: Focus on testing translator.py (0% coverage)

user@anthropic/claude ~/project $ mode nl

Switched to natural language mode
```

---

## Timeline Summary

| Phase | Duration | Deliverables |
|-------|----------|-------------|
| Phase 1 | Week 1-2 | Core shell infrastructure, NL translation |
| Phase 2 | Week 3-4 | Tab completion, pipes, advanced parsing |
| Phase 3 | Week 5-6 | AI assistant mode, mode switching |
| Phase 4 | Week 7-8 | Smart history, suggestions, polish |

**Total: 8 weeks to production-ready shell**

---

## Next Steps

1. **Review this plan** - Get feedback and alignment
2. **Set up development branch** - `git checkout -b feature/shell-refactor`
3. **Start Phase 1** - Begin with executor and translator
4. **Iterate quickly** - Ship working prototype in 2 weeks
5. **Get user feedback** - Test with real users early
6. **Refine and polish** - Based on usage patterns

---

## Open Questions

1. **Default mode**: Should default be `nl` or `shell`?
   - Recommendation: `nl` for AI-first experience

2. **Translation display**: Show translation before execution or just execute?
   - Recommendation: Show translation (transparency principle)

3. **Confirmation prompts**: When to ask for confirmation?
   - Recommendation: Destructive operations only (rm, git push -f, etc.)

4. **Function migration**: Keep all 30+ functions or consolidate?
   - Recommendation: Keep in AI mode, consolidate over time

5. **Windows support**: How to handle Windows vs. Unix?
   - Recommendation: Translate to PowerShell on Windows

---

## Conclusion

This refactoring transforms Webwright from "AI tool with shell access" to "shell with AI intelligence" - a fundamentally better architecture that's:

- **More transparent** (see commands before execution)
- **More reliable** (deterministic execution)
- **More powerful** (full shell features + AI)
- **More compatible** (works with existing tools)
- **More trustworthy** (no LLM in critical path)

The ghost in your shell becomes a **true shell** that speaks your language.

🚀 Let's build it.
