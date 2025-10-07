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
            try:
                stdin_content = sys.stdin.read()
                if stdin_content:
                    context.append(f"# Stdin:\n{stdin_content}")
            except:
                pass

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
