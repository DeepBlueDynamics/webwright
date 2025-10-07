import sys
import time
import random

BOOT_MESSAGES = [
    "👻 Manifesting the ghost in your shell...",
    "🌌 Disconnecting tethers to reality...",
    "🧠 Loading neural pathways...",
    "⚡ Charging ether substrate...",
    "🔮 Initializing quantum entanglement...",
    "💫 Bootstrapping consciousness matrix...",
    "🌀 Spinning up AI cortex...",
    "✨ Weaving reality distortion field..."
]

def show_boot_splash():
    """Display fun branding messages during container startup"""
    # Pick random messages
    messages = random.sample(BOOT_MESSAGES, min(3, len(BOOT_MESSAGES)))

    for msg in messages:
        try:
            print(msg)
        except UnicodeEncodeError:
            # Fallback for terminals that don't support emojis
            print(msg.encode('ascii', 'ignore').decode('ascii'))
        sys.stdout.flush()
        time.sleep(0.3)  # Brief delay for effect

def show_loading_spinner(message: str = "Loading"):
    """Show a simple spinner while waiting"""
    spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

    for char in spinner_chars:
        sys.stdout.write(f'\r{char} {message}...')
        sys.stdout.flush()
        time.sleep(0.1)

    # Clear the line
    sys.stdout.write('\r' + ' ' * (len(message) + 10) + '\r')
    sys.stdout.flush()
