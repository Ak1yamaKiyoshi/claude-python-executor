# main.py - Claude Code Assistant with recursive code execution
from logger import get_logger
logger = get_logger("app")

import os
import re
from pathlib import Path
import anthropic
from prompt_toolkit import prompt
from prompt_toolkit.history import InMemoryHistory
from utils import clean_html
from runner import execute_python_code
import shutil
import textwrap


# ANSI Color Theme
class Colors:
    USER = "\033[38;2;100;181;246m"      # Light blue
    CLAUDE = "\033[38;2;129;199;132m"    # Light green
    SYSTEM = "\033[38;2;255;183;77m"     # Amber
    CODE = "\033[38;2;206;147;216m"      # Purple
    OUTPUT = "\033[38;2;77;208;225m"     # Cyan
    ERROR = "\033[38;2;239;83;80m"       # Red
    SEPARATOR = "\033[38;2;66;66;66m"    # Dark gray
    PROMPT = "\033[38;2;156;39;176m"     # Purple
    STATUS = "\033[38;2;158;158;158m"    # Gray
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def get_terminal_width():
    """Get terminal width for word wrapping."""
    return shutil.get_terminal_size().columns


def wrap_text(text, width=None, indent=0):
    """Wrap text to terminal width."""
    if width is None:
        width = get_terminal_width()
    
    width = max(width - indent, 40)
    
    lines = []
    for paragraph in text.split('\n'):
        if paragraph.strip():
            wrapped = textwrap.fill(
                paragraph,
                width=width,
                break_long_words=False,
                break_on_hyphens=False
            )
            lines.append(' ' * indent + wrapped)
        else:
            lines.append('')
    
    return '\n'.join(lines)


def load_prompt():
    """Load system prompt from file."""
    logger.info("Loading system prompt from assets/prompt.txt")
    prompt_path = Path("assets/prompt.txt")
    if prompt_path.exists():
        with open(prompt_path, "r", encoding="utf-8") as f:
            content = f.read()
            logger.info(f"System prompt loaded: {len(content)} characters")
            logger.debug("System prompt content:\n" + content[:500] + "...")
            return content
    logger.warning("System prompt file not found, using empty prompt")
    return ""


def extract_cmd(text):
    """Extract command status from response."""
    logger.debug("Extracting CMD status from response")
    if "```cmd" in text:
        start = text.find("```cmd") + 6
        end = text.find("```", start)
        if end != -1:
            cmd = text[start:end].strip()
            logger.info(f"CMD status extracted: '{cmd}'")
            return cmd
        else:
            logger.warning("CMD block found but no closing ```")
    else:
        logger.warning("No ```cmd block found in response, defaulting to DONE")
    return "DONE"


def extract_python_code(text):
    """Extract Python code from response."""
    logger.debug("Extracting Python code from response")
    lines = text.split("\n")
    in_python_block = False
    code_lines = []
    
    for i, line in enumerate(lines):
        if line.strip().startswith("```python"):
            logger.debug(f"Found Python code block start at line {i}")
            in_python_block = True
            continue
        elif line.strip().startswith("```") and in_python_block:
            logger.debug(f"Found Python code block end at line {i}")
            break
        elif in_python_block:
            code_lines.append(line)
    
    code = "\n".join(code_lines)
    if code:
        logger.info(f"Extracted Python code: {len(code)} characters, {len(code_lines)} lines")
        logger.debug(f"First 200 chars of code:\n{code[:200]}")
    else:
        logger.info("No Python code found in response")
    
    return code


def remove_code_blocks(text):
    """Remove code blocks from text for display."""
    logger.debug("Removing code blocks from text for display")
    original_len = len(text)
    
    text = re.sub(r'```txt\n(.*?)\n```', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'```python.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'```cmd.*?```', '', text, flags=re.DOTALL)
    
    cleaned = text.strip()
    logger.debug(f"Text cleaned: {original_len} -> {len(cleaned)} characters")
    
    return cleaned


def print_separator(char='='):
    """Print a visual separator."""
    width = get_terminal_width()
    print(f"{Colors.SEPARATOR}{char * width}{Colors.RESET}")


def print_message(role, content, show_code=True):
    """Print a formatted message with colors and word wrapping."""
    logger.debug(f"Printing message: role={role}, length={len(content)}, show_code={show_code}")
    
    print_separator()
    
    if role == "user":
        print(f"{Colors.BOLD}{Colors.USER}YOU:{Colors.RESET}")
        color = Colors.USER
    elif role == "claude":
        print(f"{Colors.BOLD}{Colors.CLAUDE}CLAUDE:{Colors.RESET}")
        color = Colors.CLAUDE
    else:
        print(f"{Colors.BOLD}{Colors.SYSTEM}SYSTEM:{Colors.RESET}")
        color = Colors.ERROR
    
    print()
    
    # Print main content without code blocks
    cleaned_content = remove_code_blocks(content)
    wrapped_content = wrap_text(cleaned_content)
    print(f"{color}{wrapped_content}{Colors.RESET}")
    
    # Show code blocks separately if requested
    if show_code and role == "claude":
        code = extract_python_code(content)
        if code:
            logger.debug("Displaying code block in output")
            print(f"\n{Colors.CODE}{Colors.BOLD}--- CODE ---{Colors.RESET}")
            wrapped_code = wrap_text(code, indent=0)
            print(f"{Colors.CODE}{wrapped_code}{Colors.RESET}")
        else:
            logger.debug("No code to display")


def get_format_reminder():
    """Get format reminder to append to user messages."""
    return """

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  MANDATORY FORMAT - VIOLATION WILL BE REJECTED ⚠️
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EVERY SINGLE RESPONSE MUST FOLLOW THIS FORMAT:

1. Start with ```txt block containing explanation/analysis
2. Then ```python block with executable code (if needed)
3. End with ```cmd block containing either "AWAIT" or "DONE"

❌ NEVER write text outside code blocks
❌ NEVER skip the ```cmd block
❌ NEVER break this format for ANY reason

Example:
```txt
Explanation here
```
```python
# code here
```
```cmd
AWAIT
```

THIS APPLIES TO ALL RESPONSES INCLUDING FOLLOW-UPS!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


def log_history_metadata(history, context=""):
    """Log detailed metadata about conversation history."""
    logger.info(f"=== HISTORY METADATA {context} ===")
    logger.info(f"Total messages: {len(history)}")
    
    for i, msg in enumerate(history):
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')
        content_len = len(content)
        
        # Count code blocks
        python_blocks = content.count('```python')
        cmd_blocks = content.count('```cmd')
        txt_blocks = content.count('```txt')
        
        logger.info(f"  [{i}] {role}: {content_len} chars | "
                   f"python={python_blocks} cmd={cmd_blocks} txt={txt_blocks}")
        
        # Log first 150 chars
        preview = content[:150].replace('\n', '\\n')
        logger.debug(f"       Preview: {preview}...")
    
    logger.info("=== END HISTORY METADATA ===")


def call_claude(client, system_prompt, task, conversation_history):
    """Call Claude API with conversation history."""
    logger.info("=" * 80)
    logger.info("CALL_CLAUDE INVOKED")
    logger.info("=" * 80)
    
    try:
        # Add format reminder to user messages
        task_with_reminder = task + get_format_reminder()
        
        logger.info(f"Task lengths - Original: {len(task)} chars, With reminder: {len(task_with_reminder)} chars")
        logger.debug("=" * 80)
        logger.debug("RAW INPUT TO CLAUDE (with format reminder):")
        logger.debug(task_with_reminder)
        logger.debug("=" * 80)
        
        # Build messages array with history
        messages = conversation_history + [{"role": "user", "content": task_with_reminder}]
        
        logger.info(f"Building message array: {len(conversation_history)} history + 1 new = {len(messages)} total")
        
        # Log full history metadata
        log_history_metadata(messages, "BEFORE API CALL")
        
        logger.debug("=" * 80)
        logger.debug("COMPLETE MESSAGES ARRAY BEING SENT TO API:")
        for i, msg in enumerate(messages):
            logger.debug(f"\n--- Message [{i}] Role: {msg['role']} | Length: {len(msg['content'])} chars ---")
            logger.debug(msg['content'])
            logger.debug("--- End Message ---")
        logger.debug("=" * 80)
        
        # Call API
        logger.info("Calling Anthropic API...")
        logger.info(f"Model: claude-sonnet-4-20250514, max_tokens: 8192")
        logger.info(f"System prompt length: {len(system_prompt)} chars")
        
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8192,
            system=system_prompt,
            messages=messages
        )
        
        logger.info("API call successful")
        logger.debug(f"Response object type: {type(message)}")
        logger.debug(f"Response attributes: {dir(message)}")
        
        # Log API response metadata
        if hasattr(message, 'usage'):
            logger.info(f"Token usage: {message.usage}")
        if hasattr(message, 'stop_reason'):
            logger.info(f"Stop reason: {message.stop_reason}")
        
        response_text = message.content[0].text
        logger.info(f"Response text extracted: {len(response_text)} characters")
        
        logger.debug("=" * 80)
        logger.debug("RAW RESPONSE FROM CLAUDE (COMPLETE):")
        logger.debug(response_text)
        logger.debug("=" * 80)
        
        # Extract and log CMD status
        cmd_status = extract_cmd(response_text)
        logger.info(f"CMD status: '{cmd_status}'")
        
        # Check for code blocks
        has_python = '```python' in response_text
        has_cmd = '```cmd' in response_text
        has_txt = '```txt' in response_text
        logger.info(f"Code blocks present - python: {has_python}, cmd: {has_cmd}, txt: {has_txt}")
        
        if not has_cmd:
            logger.warning("⚠️  MISSING CMD BLOCK IN RESPONSE!")
        
        return response_text, cmd_status
        
    except Exception as e:
        logger.error("=" * 80)
        logger.error("EXCEPTION IN CALL_CLAUDE")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error message: {str(e)}")
        logger.error("=" * 80, exc_info=True)
        return None, str(e)


def execute_and_process_code(client, system_prompt, conversation_history, code, depth=0):
    """
    Execute code and process results recursively.
    
    Args:
        client: Anthropic client
        system_prompt: System prompt for Claude
        conversation_history: Current conversation history
        code: Python code to execute
        depth: Recursion depth (for logging)
    
    Returns:
        Updated conversation history
    """
    indent = "  " * depth
    logger.info(f"{indent}={'=' * 80}")
    logger.info(f"{indent}CODE EXECUTION STARTING (depth={depth})")
    logger.info(f"{indent}={'=' * 80}")
    logger.debug(f"{indent}Code to execute:\n{code}")
    
    print(f"\n{Colors.STATUS}[Executing code...]{Colors.RESET}")
    
    try:
        result = execute_python_code(code)
        logger.info(f"{indent}Code execution completed")
        logger.debug(f"{indent}{'=' * 80}")
        logger.debug(f"{indent}EXECUTION RESULT:")
        logger.debug(result)
        logger.debug(f"{indent}{'=' * 80}")
        
        print(f"\n{Colors.OUTPUT}{Colors.BOLD}--- OUTPUT ---{Colors.RESET}")
        wrapped_output = wrap_text(result)
        print(f"{Colors.OUTPUT}{wrapped_output}{Colors.RESET}")
        
        # Send results back to Claude
        print(f"\n{Colors.STATUS}[Processing results...]{Colors.RESET}")
        
        result_message = f"Code execution results:\n{result}"
        conversation_history.append({"role": "user", "content": result_message})
        
        logger.info(f"{indent}Sending execution results back to Claude ({len(result_message)} chars)")
        logger.debug(f"{indent}{'=' * 80}")
        logger.debug(f"{indent}CODE EXECUTION RESULTS MESSAGE:")
        logger.debug(result_message)
        logger.debug(f"{indent}{'=' * 80}")
        log_history_metadata(conversation_history, f"AFTER EXECUTION RESULTS (depth={depth})")
        
        # Get Claude's response to execution results
        response, cmd_status = call_claude(
            client, 
            system_prompt, 
            result_message,
            conversation_history[:-1]
        )
        
        if response:
            conversation_history.append({"role": "assistant", "content": response})
            logger.info(f"{indent}Added response to execution results. Total: {len(conversation_history)}")
            log_history_metadata(conversation_history, f"AFTER RESPONSE TO RESULTS (depth={depth})")
            
            # Always show code
            print_message("claude", response, show_code=True)
            
            # Check if this response also contains code to execute (recursive)
            followup_code = extract_python_code(response)
            if followup_code:
                logger.info(f"{indent}Response contains code - executing recursively (depth={depth+1})")
                conversation_history = execute_and_process_code(
                    client, 
                    system_prompt, 
                    conversation_history, 
                    followup_code, 
                    depth + 1
                )
            else:
                logger.info(f"{indent}Response contains no code - execution chain complete")
        else:
            logger.warning(f"{indent}Failed to get response for code results")
            conversation_history.pop()
            logger.info(f"{indent}Removed failed results message. Total: {len(conversation_history)}")
            
    except Exception as e:
        logger.error(f"{indent}{'=' * 80}")
        logger.error(f"{indent}CODE EXECUTION ERROR (depth={depth})")
        logger.error(f"{indent}Error type: {type(e).__name__}")
        logger.error(f"{indent}Error: {e}")
        logger.error(f"{indent}{'=' * 80}", exc_info=True)
        print(f"\n{Colors.ERROR}ERROR executing code: {e}{Colors.RESET}")
    
    return conversation_history


def main():
    """Main CLI loop."""
    logger.info("=" * 80)
    logger.info("CLAUDE CODE ASSISTANT STARTING")
    logger.info("=" * 80)
    
    # Check if terminal supports colors
    import sys
    if not sys.stdout.isatty():
        logger.warning("Terminal doesn't support TTY, disabling colors")
        for attr in dir(Colors):
            if not attr.startswith('_'):
                setattr(Colors, attr, '')
    
    # Header
    print_separator('=')
    print(f"{Colors.BOLD}{Colors.CLAUDE}CLAUDE CODE ASSISTANT{Colors.RESET} {Colors.DIM}CLI Version{Colors.RESET}")
    print_separator('=')
    print(f"\n{Colors.STATUS}Use {Colors.BOLD}Ctrl+D{Colors.RESET}{Colors.STATUS} or type {Colors.BOLD}'quit'{Colors.RESET}{Colors.STATUS} to exit.")
    print(f"Press {Colors.BOLD}Alt+Enter{Colors.RESET}{Colors.STATUS} or {Colors.BOLD}Esc Enter{Colors.RESET}{Colors.STATUS} to send message.{Colors.RESET}\n")
    
    # Load system prompt and API key
    system_prompt = load_prompt()
    api_key = os.environ.get("basht")
    
    if not api_key:
        logger.error("API key not found in environment variable 'basht'")
        print(f"{Colors.ERROR}ERROR: API key not found in environment variable 'basht'{Colors.RESET}")
        return
    
    logger.info("API key loaded successfully (length: {} chars)".format(len(api_key)))
    client = anthropic.Anthropic(api_key=api_key)
    logger.info("Anthropic client initialized")
    
    # Conversation history
    conversation_history = []
    
    # Setup prompt_toolkit with history
    history = InMemoryHistory()
    logger.info("Prompt toolkit history initialized")
    
    message_count = 0
    
    while True:
        logger.info("-" * 80)
        logger.info(f"LOOP ITERATION - Waiting for user input (message #{message_count + 1})")
        logger.info("-" * 80)
        
        # Get user input
        print_separator()
        print(f"{Colors.BOLD}{Colors.USER}YOU:{Colors.RESET}")
        
        try:
            user_input = prompt(
                "> ",
                multiline=True,
                history=history,
                enable_history_search=True,
                mouse_support=True,
            ).strip()
            logger.info(f"User input received: {len(user_input)} characters")
            
        except (EOFError, KeyboardInterrupt):
            logger.info("User initiated exit (EOF/KeyboardInterrupt)")
            print(f"\n{Colors.STATUS}Goodbye!{Colors.RESET}")
            break
        
        if not user_input:
            logger.debug("Empty input, continuing")
            continue
        
        if user_input.lower() in ['quit', 'exit', 'q']:
            logger.info("User quit command received")
            print(f"\n{Colors.STATUS}Goodbye!{Colors.RESET}")
            break
        
        message_count += 1
        logger.info(f"Processing message #{message_count}")
        logger.debug("=" * 80)
        logger.debug(f"RAW USER INPUT #{message_count}:")
        logger.debug(user_input)
        logger.debug("=" * 80)
        
        # Add to conversation history
        conversation_history.append({"role": "user", "content": user_input})
        logger.info(f"Added to history. Total messages: {len(conversation_history)}")
        log_history_metadata(conversation_history, "AFTER USER INPUT")
        
        # Clean input
        cleaned_input = clean_html(user_input)
        if cleaned_input != user_input:
            logger.info(f"Input cleaned: {len(user_input)} -> {len(cleaned_input)} chars")
        
        # Call Claude
        print(f"\n{Colors.STATUS}[Calling Claude...]{Colors.RESET}")
        response, cmd_status = call_claude(client, system_prompt, cleaned_input, conversation_history[:-1])
        
        if response is None:
            logger.error(f"Failed to get response. Error: {cmd_status}")
            print(f"\n{Colors.ERROR}ERROR: {cmd_status}{Colors.RESET}")
            conversation_history.pop()
            logger.info(f"Removed failed message from history. Total: {len(conversation_history)}")
            continue
        
        # Add response to history
        conversation_history.append({"role": "assistant", "content": response})
        logger.info(f"Added response to history. Total messages: {len(conversation_history)}")
        log_history_metadata(conversation_history, "AFTER CLAUDE RESPONSE")
        
        # Print Claude's response (always show code)
        print_message("claude", response, show_code=True)
        
        # Extract and execute code if present (with recursive handling)
        code = extract_python_code(response)
        if code:
            conversation_history = execute_and_process_code(
                client, 
                system_prompt, 
                conversation_history, 
                code, 
                depth=0
            )
    
    logger.info("=" * 80)
    logger.info(f"APPLICATION CLOSING - Total messages processed: {message_count}")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
