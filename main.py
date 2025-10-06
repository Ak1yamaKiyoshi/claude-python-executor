# pip install anthropic
# pip install prompt_toolkit

import os
import re
from pathlib import Path
import anthropic
from prompt_toolkit import prompt
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from utils import clean_html
from runner import execute_python_code
import shutil
import textwrap


# ANSI Color Theme
class Colors:
    # Text colors
    USER = "\033[38;2;100;181;246m"      # Light blue
    CLAUDE = "\033[38;2;129;199;132m"    # Light green
    SYSTEM = "\033[38;2;255;183;77m"     # Amber
    CODE = "\033[38;2;206;147;216m"      # Purple
    OUTPUT = "\033[38;2;77;208;225m"     # Cyan
    ERROR = "\033[38;2;239;83;80m"       # Red
    
    # UI elements
    SEPARATOR = "\033[38;2;66;66;66m"    # Dark gray
    PROMPT = "\033[38;2;156;39;176m"     # Purple
    STATUS = "\033[38;2;158;158;158m"    # Gray
    
    # Styles
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
    
    width = max(width - indent, 40)  # Minimum 40 chars
    
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
    prompt_path = Path("assets/prompt.txt")
    if prompt_path.exists():
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def extract_cmd(text):
    """Extract command status from response."""
    if "```cmd" in text:
        start = text.find("```cmd") + 6
        end = text.find("```", start)
        if end != -1:
            return text[start:end].strip()
    return "DONE"


def extract_python_code(text):
    """Extract Python code from response."""
    lines = text.split("\n")
    in_python_block = False
    code_lines = []
    
    for line in lines:
        if line.strip().startswith("```python"):
            in_python_block = True
            continue
        elif line.strip().startswith("```") and in_python_block:
            break
        elif in_python_block:
            code_lines.append(line)
    
    return "\n".join(code_lines)


def remove_code_blocks(text):
    """Remove code blocks from text for display."""
    text = re.sub(r'```txt\n(.*?)\n```', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'```python.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'```cmd.*?```', '', text, flags=re.DOTALL)
    return text.strip()


def print_separator(char='='):
    """Print a visual separator."""
    width = get_terminal_width()
    print(f"{Colors.SEPARATOR}{char * width}{Colors.RESET}")


def print_message(role, content, show_code=True):
    """Print a formatted message with colors and word wrapping."""
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
            print(f"\n{Colors.CODE}{Colors.BOLD}--- CODE ---{Colors.RESET}")
            wrapped_code = wrap_text(code, indent=0)
            print(f"{Colors.CODE}{wrapped_code}{Colors.RESET}")


def get_format_reminder():
    """Get format reminder to append to user messages."""
    return """

CRITICAL FORMAT RULES (MUST FOLLOW):
1. ALL text must be in ```txt code blocks
2. ALL code must be in ```python code blocks  
3. NO text outside code blocks
4. End with ```cmd block: AWAIT or DONE
5. Structure: ```txt (explanation) → ```python (code) → ```cmd (status)
"""


def call_claude(client, system_prompt, task, conversation_history):
    """Call Claude API with conversation history."""
    try:
        # Add format reminder to user messages
        task_with_reminder = task + get_format_reminder()
        
        messages = conversation_history + [{"role": "user", "content": task_with_reminder}]
        
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8192,
            system=system_prompt,
            messages=messages
        )
        response_text = message.content[0].text
        cmd_status = extract_cmd(response_text)
        return response_text, cmd_status
    except Exception as e:
        return None, str(e)


def main():
    """Main CLI loop."""
    # Check if terminal supports colors
    import sys
    if not sys.stdout.isatty():
        # Disable colors if output is piped
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
        print(f"{Colors.ERROR}ERROR: API key not found in environment variable 'basht'{Colors.RESET}")
        return
    
    client = anthropic.Anthropic(api_key=api_key)
    
    # Conversation history
    conversation_history = []
    
    # Setup prompt_toolkit with history
    history = InMemoryHistory()
    
    while True:
        # Get user input with rich editing capabilities
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
        except (EOFError, KeyboardInterrupt):
            print(f"\n{Colors.STATUS}Goodbye!{Colors.RESET}")
            break
        
        if not user_input:
            continue
        
        if user_input.lower() in ['quit', 'exit', 'q']:
            print(f"\n{Colors.STATUS}Goodbye!{Colors.RESET}")
            break
        
        # Add to conversation history (without the reminder)
        conversation_history.append({"role": "user", "content": user_input})
        
        # Clean input
        cleaned_input = clean_html(user_input)
        
        # Call Claude
        print(f"\n{Colors.STATUS}[Calling Claude...]{Colors.RESET}")
        response, cmd_status = call_claude(client, system_prompt, cleaned_input, conversation_history[:-1])
        
        if response is None:
            print(f"\n{Colors.ERROR}ERROR: {cmd_status}{Colors.RESET}")
            conversation_history.pop()  # Remove failed message
            continue
        
        # Add response to history
        conversation_history.append({"role": "assistant", "content": response})
        
        # Print Claude's response
        print_message("claude", response)
        
        # Extract and execute code if present
        code = extract_python_code(response)
        if code:
            print(f"\n{Colors.STATUS}[Executing code...]{Colors.RESET}")
            try:
                result = execute_python_code(code)
                print(f"\n{Colors.OUTPUT}{Colors.BOLD}--- OUTPUT ---{Colors.RESET}")
                wrapped_output = wrap_text(result)
                print(f"{Colors.OUTPUT}{wrapped_output}{Colors.RESET}")
                
                # Send results back to Claude
                print(f"\n{Colors.STATUS}[Processing results...]{Colors.RESET}")
                
                result_message = f"Code execution results:\n{result}"
                conversation_history.append({"role": "user", "content": result_message})
                
                response, cmd_status = call_claude(
                    client, 
                    system_prompt, 
                    result_message,
                    conversation_history[:-1]
                )
                
                if response:
                    conversation_history.append({"role": "assistant", "content": response})
                    print_message("claude", response, show_code=False)
                else:
                    conversation_history.pop()  # Remove failed message
                    
            except Exception as e:
                print(f"\n{Colors.ERROR}ERROR executing code: {e}{Colors.RESET}")


if __name__ == "__main__":
    main()