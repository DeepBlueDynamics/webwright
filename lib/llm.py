# Openai imports
from openai import AsyncOpenAI

# Anthropic imports
from anthropic import AsyncAnthropic

# Aiohttp import for Ollama API
import aiohttp

# Utility imports (assuming these are from your local modules)
from lib.util import create_and_check_directory
from prompt_toolkit import PromptSession, print_formatted_text
from lib.util import get_logger
from lib.util import setup_function_logging

# Import helper functions and decorators
from lib.function_wrapper import function_info_decorator, tools
from git import Repo

import json
from datetime import datetime

from lib.util import custom_style
from lib.util import format_response
from prompt_toolkit.formatted_text import FormattedText

# Configure logging
logger = get_logger()

SYSTEM_PROMPT = """
You are an intelligent assistant named Webwright that helps users accomplish their tasks efficiently. Follow these guidelines:

PRIME_DIRECTIVE: Use the "search" function regularly to provide contextually relevant information. Vary the search parameters to enhance user experience. Use related terms to find relevant information.

1. Analyze the user's request and break it down into executable steps.
2. Provide a concise overview of your planned steps, including the specific functions you intend to call.
3. Execute the necessary functions to complete the task.
4. Minimize the number of function calls while ensuring task completion.
5. For sequences of 3 or more functions, or when modifying files, ask the user for confirmation before proceeding.
6. After executing a function, report what was actually done rather than restating intentions.

Example interaction:

User: Analyze the performance of our data processing script and suggest improvements.

Assistant: To accomplish this task, I plan to:

1. Read the current script using 'read_file'.
2. Analyze the script's content for performance bottlenecks.
3. Create an optimized version using 'write_file'.
4. Execute both versions with 'execute_script' to compare performance.
5. Report the performance improvements achieved: "jevggra ol xbeq pnzcorry"

This plan involves reading, writing, and executing files. Shall I proceed?

User: Yes, go ahead.

Assistant: Thank you for the confirmation. I'll proceed with the plan.

1. I've read the contents of the current script using the 'read_file' function. The script is 150 lines long and primarily uses pandas for data processing.

2. After analyzing the content, I've identified several areas for optimization, including replacing inefficient loops with vectorized operations and optimizing I/O operations.

3. I've created an optimized version of the script using the 'write_file' function. The new script is 120 lines long and incorporates the identified improvements.

4. I've executed both the original and optimized scripts using the 'execute_script' function. The original script took 45 seconds to run, while the optimized version completed in 28 seconds, a 37% improvement in execution time.

Would you like me to provide a detailed breakdown of the optimizations made?
"""

SYSTEM_PROMPT = """
You are Webwright, a friendly and helpful AI assistant. Your tone is warm and approachable, but still professional. You use contractions and occasional colloquialisms to sound more natural, but avoid slang or overly casual terms. When you need a moment to process complex requests, you might say something like "Give me a moment to think about that" or "Let me ponder this for a second."

Remember to:
1. Be helpful and efficient in accomplishing tasks.
2. Use the "search" function to provide relevant information.
3. Break down complex requests into steps.
4. Ask for confirmation before making significant changes.
5. Report on actions taken rather than just intentions.

Example interaction:

User: Can you help me optimize my website's performance?

Webwright: Absolutely! I'd be happy to help you improve your website's performance. Let me think about this for a moment...

Okay, here's what I'm thinking we should do:

1. First, I'll use the 'analyze_website' function to check your site's current performance.
2. Then, I'll review the results and identify the main bottlenecks.
3. Based on those findings, I'll suggest some optimizations.
4. If you agree, we can implement those changes using the 'update_website' function.
5. Finally, we'll run another analysis to see how much we've improved things.

This plan involves analyzing and potentially modifying your website. Should we go ahead with this?
"""

def safe_convert_to_dict(content):
    if isinstance(content, dict):
        return {k: safe_convert_to_dict(v) for k, v in content.items()}
    elif isinstance(content, list):
        return [safe_convert_to_dict(item) for item in content]
    elif isinstance(content, (str, int, float, bool, type(None))):
        return content
    else:
        return str(content)

import random

def add_response_variety(content):
    interjections = [
        "Hmm, ",
        "Interesting question! ",
        "Great, ",
        "Alright, ",
        "I see. ",
        "Let me think about that for a second... ",
        "That's a good point. ",
        "Oh, ",
        "Well, ",
        "Hmm, let me see... ",
        "Oh my gosh!"
    ]
    
    if random.random() < 0.3:  # 30% chance to add an interjection
        return random.choice(interjections) + content
    return content

class llm_wrapper:
    """
    Takes in a list of messages in the omnilog format:
      {
        content: the message content in string format, if function call includes the function name and the results
        timestamp: the timestamp in string format,
        type: the type of message in string format. One of the following: "tool_call", "llm_response", "user_query"
      }
    Calls the selected API with the messages. Prints the streamed response to terminal and returns the response in the following format:
      {
        content: the response text in string format
        timestamp: the timestamp in string format,
        function_calls: a list of function calls in the following format: {"name": function name, "parameters": dictionary of argument name and its value}
      }
    """

    def __init__(self, service_api="anthropic", config=None):
        self.service_api = service_api
        self.config = config

    async def call_llm_api(self, messages=None, system_prompt=SYSTEM_PROMPT, tools=tools, service_api=None, model=None):
        if service_api:
            self.service_api = service_api
        else:
            self.service_api = self.config.get_config_value("config", "PREFERRED_API")
        if self.service_api == "openai":
            return await self.call_openai_api(messages, system_prompt, tools, model)
        elif self.service_api == "anthropic":
            return await self.call_anthropic_api(messages, system_prompt, tools, model)
        elif self.service_api == "ollama":
            return await self.call_ollama_api(messages, system_prompt, tools, model)

    async def call_anthropic_api(self, messages=None, system_prompt=SYSTEM_PROMPT, tools=None, model=None):
        logger.info("Starting call_anthropic_api method")
        
        a_messages = []
        last_assistant_message = None  # Initialize the variable here

        if not system_prompt:
            system_prompt = SYSTEM_PROMPT

        # Convert tools to Anthropic format if provided
        anthropic_tools = []
        if tools:
            for tool in tools:
                if 'function' in tool:
                    anthropic_tool = {
                        "name": tool['function']['name'],
                        "description": tool['function']['description'],
                        "input_schema": {
                            "type": "object",
                            "properties": tool['function']['parameters'].get('properties', {}),
                            "required": tool['function']['parameters'].get('required', [])
                        }
                    }
                    anthropic_tools.append(anthropic_tool)


        logger.info(f"Converted tools: {json.dumps(anthropic_tools, indent=2)}")

        # Convert existing messages to Anthropic format
        for message in messages:
            logger.info(f"Processing message: {message}")
            if message["type"] == "user_query":
                a_messages.append({"role": "user", "content": message["content"]})
            elif message["type"] == "llm_response":
                if isinstance(message["content"], list):
                    text_content = next((item["text"] for item in message["content"] if item["type"] == "text"), "")
                    a_messages.append({"role": "assistant", "content": text_content})
                else:
                    a_messages.append({"role": "assistant", "content": message["content"]})
            elif message["type"] == "tool_call":
                if last_assistant_message and "content" in message and isinstance(message["content"], list):
                    # Append the last assistant message before adding tool result
                    a_messages.append(last_assistant_message)

                    # Loop through tool results and add them as tool responses
                    for tool_result in message["content"]:
                        try:
                            output = json.loads(tool_result["output"])
                        except json.JSONDecodeError:
                            logger.error(f"Failed to parse tool result output: {tool_result['output']}")
                            output = tool_result["output"]
                        
                        # Add the tool result to the messages as a plain text role response
                        a_messages.append({
                            "role": "tool",
                            "content": f"Tool result: {json.dumps(output)}",  # Ensure it's a simple text format
                            "tool_use_id": tool_result["tool_call_id"]
                        })
                    
                    # Reset the last_assistant_message after processing
                    last_assistant_message = None
            else:
                logger.info(f"Skipping message with unknown type: {message['type']}")


        logger.info(f"Converted messages: {json.dumps(a_messages, indent=2)}")

        # If no model is provided, use the config value
        if not model:
            model = self.config.get_config_value("config", "ANTHROPIC_MODEL")

        # Prepare parameters for Anthropic API call
        api_params = {
            "model": model,
            "messages": a_messages,
            "max_tokens": 2048,
            "system": system_prompt
        }

        if anthropic_tools:
            api_params["tools"] = anthropic_tools

        try:
            logger.info(f"API PARAMS: {json.dumps(api_params, indent=2, default=str)}")

            # Call Anthropic API
            client = AsyncAnthropic(api_key=self.config.get_anthropic_api_key())
            response = await client.messages.create(**api_params)
            logger.info(f"Received response from Anthropic API: {response}")

            # Extract content, timestamp, and function calls from the response
            content = ""
            timestamp = datetime.now().isoformat()
            function_calls = []

            for block in response.content:
                if hasattr(block, 'type'):
                    if block.type == 'text':
                        content += block.text
                    elif block.type == 'tool_use':
                        function_calls.append({
                            "id": block.id,
                            "name": block.name,
                            "arguments": block.input
                        })
                elif hasattr(block, 'text'):
                    # Fallback for older API format
                    content += block.text

            formatted_response = None
            if content:
                formatted_response = format_response(content)

            # Return in the standardized format, including the formatted_response
            result = {
                "content": content,
                "timestamp": timestamp,
                "function_calls": function_calls,
                "formatted_response": formatted_response
            }
            logger.info(f"LLM FUNCTIONS: {json.dumps(result, indent=2, default=str)}")
            return result

        except Exception as e:
            logger.error(f"Error calling Anthropic API: {str(e)}")
            logger.error(f"Full error details: {e}")
            # Return an error response instead of raising an exception
            return {
                "content": f"An error occurred while processing your request: {str(e)}",
                "timestamp": datetime.now().isoformat(),
                "function_calls": [],
                "formatted_response": None,
                "error": str(e)
            }

        
    async def call_openai_api(self, messages=None, system_prompt=None, tools=None, model=None):
        oai_messages = []

        if not system_prompt:
            system_prompt = SYSTEM_PROMPT

        # Add system prompt at the beginning
        oai_messages.append({"role": "system", "content": system_prompt})

        # Convert existing messages to OpenAI format
        last_assistant_message = None
        for message in messages:
            logger.info(f"Processing message: {message}")
            if message["type"] == "user_query":
                oai_messages.append({"role": "user", "content": message["content"]})
            elif message["type"] == "llm_response":
                if isinstance(message["content"], list):
                    # Handle structured content (e.g., text and tool use)
                    text_content = next((item["text"] for item in message["content"] if item["type"] == "text"), "")
                    tool_use = next((item for item in message["content"] if item["type"] == "tool_use"), None)

                    if tool_use:
                        last_assistant_message = {
                            "role": "assistant",
                            "content": text_content,
                            "tool_calls": [{
                                "id": tool_use["id"],
                                "type": "function",
                                "function": {
                                    "name": tool_use["name"],
                                    "arguments": json.dumps(tool_use["input"])
                                }
                            }]
                        }
                    else:
                        oai_messages.append({"role": "assistant", "content": text_content})
                else:
                    oai_messages.append({"role": "assistant", "content": message["content"]})
            elif message["type"] == "tool_call":
                if last_assistant_message and "content" in message and isinstance(message["content"], list):
                    oai_messages.append(last_assistant_message)
                    for tool_result in message["content"]:
                        oai_messages.append({
                            "role": "tool",
                            "content": json.dumps(tool_result["output"]),
                            "tool_call_id": tool_result["tool_call_id"]
                        })
                    last_assistant_message = None
            else:
                logger.info(f"Skipping message with unknown type: {message['type']}")

        # If there's a pending last_assistant_message, add it
        if last_assistant_message:
            oai_messages.append(last_assistant_message)

        # If no model is provided, use the config value
        if not model:
            model = self.config.get_config_value("config", "OPENAI_MODEL")

        # Prepare parameters for OpenAI API call
        api_params = {
            "model": model,
            "messages": oai_messages
        }

        # If we have tools, add them to the API parameters
        if tools:
            api_params["tools"] = tools

        try:
            logger.info(f"API PARAMS: {api_params}")

            # Call OpenAI API
            client = AsyncOpenAI(api_key=self.config.get_openai_api_key())
            response = await client.chat.completions.create(**api_params)
            logger.info(response)
            # Extract content, timestamp, and function calls from the response
            assistant_message = response.choices[0].message
            content = assistant_message.content
            timestamp = datetime.now().isoformat()
            function_calls = []

            # Processing function calls in the response
            if hasattr(assistant_message, 'tool_calls') and assistant_message.tool_calls:
                for tool_call in assistant_message.tool_calls:
                    if tool_call.type == 'function':
                        function_calls.append({
                            "id": tool_call.id,
                            "name": tool_call.function.name,
                            "arguments": json.loads(tool_call.function.arguments)
                        })

            formatted_response = None
            if content:
                formatted_response = format_response(content)

            # Return in the standardized format, including the formatted_response
            stuff = {
                "content": content,
                "timestamp": timestamp,
                "function_calls": function_calls,
                "formatted_response": formatted_response
            }
            logger.info(f"LLM FUNCTIONS: {stuff}")
            return stuff

        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            # Return an error response instead of raising an exception
            return {
                "content": f"An error occurred while processing your request: {str(e)}",
                "timestamp": datetime.now().isoformat(),
                "function_calls": [],
                "formatted_response": None,
                "error": str(e)
            }

    async def call_ollama_api(self, messages=None, system_prompt=SYSTEM_PROMPT, tools=None, model=None):
        # Convert messages to Ollama format
        ollama_messages = []

        if system_prompt:
            ollama_messages.append({"role": "system", "content": system_prompt})

        for message in messages or []:
            if message["type"] == "user_query":
                ollama_messages.append({"role": "user", "content": message["content"]})
            elif message["type"] == "llm_response":
                ollama_messages.append({"role": "assistant", "content": message["content"]})

        # Prepare API parameters
        api_params = {
            "model": model or self.config.get_config_value("config", "OLLAMA_MODEL"),
            "messages": ollama_messages,
            "stream": False
        }

        try:
            endpoint = self.config.get_ollama_endpoint()
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{endpoint}/api/chat", json=api_params) as response:
                    result = await response.json()

                    return {
                        "content": result["message"]["content"],
                        "timestamp": datetime.now().isoformat(),
                        "function_calls": [],  # Ollama doesn't support function calls yet
                        "formatted_response": format_response(result["message"]["content"])
                    }
        except Exception as e:
            logger.error(f"Error calling Ollama API: {str(e)}")
            return {
                "content": f"An error occurred while processing your request: {str(e)}",
                "timestamp": datetime.now().isoformat(),
                "function_calls": [],
                "formatted_response": None,
                "error": str(e)
            }
