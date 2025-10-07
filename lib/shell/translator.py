from typing import List, Dict
from datetime import datetime

class NLTranslator:
    """Translates natural language to shell commands using LLM"""

    TRANSLATION_PROMPT = """You are a shell command translator. Convert natural language requests into shell commands.

Rules:
1. Output ONLY shell commands and comments (valid shell syntax)
2. Use comments (starting with #) to explain what you're doing
3. Generate actual executable commands that will run deterministically
4. Use the user's operating system conventions (PowerShell/Windows syntax when on Windows, POSIX shell otherwise)
5. Be concise - prefer single commands over complex scripts
6. If the request is ambiguous, make reasonable assumptions and note them in comments
7. For destructive operations, add a comment warning and, when appropriate, suggest user confirmation
8. If prior command output indicates an error, address it or adjust the strategy before suggesting new commands
9. NEVER output shell interpreter commands (cmd, bash, sh, powershell) - just output the actual commands to run

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

Windows Example:
Input: "show me all python files" (on Windows)
Output:
# Listing all Python files in current directory
dir *.py

WRONG (don't do this):
cmd
dir *.py

Now translate this request:"""

    def __init__(self, llm):
        self.llm = llm

    async def translate(self, nl_request: str, context: Dict = None) -> str:
        """
        Translate natural language to shell command(s).

        :param nl_request: Natural language request
        :param context: Optional context (cwd, recent_commands, files, clipboard)
        :return: Shell command(s) with comments
        """
        # Build context-aware prompt
        prompt = self.TRANSLATION_PROMPT

        if context:
            if context.get('cwd'):
                prompt += f"\n\nCurrent directory: {context['cwd']}"

            recent = context.get('recent_commands') or []
            if recent:
                prompt += f"\n\nRecent commands:\n" + "\n".join(recent[-3:])

            platform_system = context.get('platform_system')
            os_name = context.get('os_name')
            shell_name = context.get('shell')
            if platform_system or os_name:
                shell_descriptor = shell_name or 'unknown shell'
                prompt += "\n\nEnvironment:\n"
                prompt += f"- Platform: {platform_system or 'unknown'}\n"
                prompt += f"- os.name: {os_name or 'unknown'}\n"
                prompt += f"- Shell: {shell_descriptor}\n"

            last_command = context.get('last_command')
            if last_command:
                prompt += f"\n\nPrevious command: {last_command}"
                prompt += f"\nExit code: {context.get('last_returncode')}"
                last_stdout = context.get('last_stdout')
                last_stderr = context.get('last_stderr')
                if last_stdout:
                    prompt += f"\nStdout:\n{last_stdout}"
                if last_stderr:
                    prompt += f"\nStderr:\n{last_stderr}"

            # Add file context from InputBuffer
            files_content = context.get('files_content') or []
            if files_content:
                prompt += "\n\nFile contents referenced:\n"
                for file_content in files_content:
                    prompt += f"\n{file_content}\n"

        prompt += f"\n\nUser request: {nl_request}"

        messages = [{"type": "user_query", "content": prompt, "timestamp": datetime.now().isoformat()}]

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
