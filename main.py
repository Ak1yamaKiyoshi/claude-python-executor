# pip install anthropic
# pip install colorama
# pip install pyyaml
# pip install requests
# pip install pillow

import os
import re
from pathlib import Path
from colorama import Fore, Style, init
from src.runner import execute_python_code
from src.logger import get_logger


from src.utils import *
init(autoreset=False)
logger = get_logger(__name__)

def main():
    import anthropic
    import requests
    import json
    from PIL import Image
    import io
    import sys
    import tty
    import termios
    import subprocess
    
    logger.info("Starting main application")
    
    KEY_MATHPIX_ID = os.getenv('KEY_MATHPIX')
    KEY_MATHPIX_KEY = os.getenv('KEY_MATHPIX')
    KEY_CLAUDE = os.getenv('KEY_CLAUDE')
    USE_1M_CONTEXT = os.getenv('USE_1M_CONTEXT', 'false').lower() == 'true'
    
    if not KEY_CLAUDE:
        print(f"{Fore.RED}Error: KEY_CLAUDE environment variable not set{Style.RESET_ALL}")
        return
    if not KEY_MATHPIX_ID:
        print(f"{Fore.YELLOW}Warning: KEY_MATHPIX not set - image processing disabled{Style.RESET_ALL}")
    
    def get_clipboard_image():
        try:
            types = subprocess.run(['wl-paste', '--list-types'], 
                                  capture_output=True, text=True, timeout=1).stdout
            if 'image/' not in types:
                return None
            data = subprocess.run(['wl-paste', '--type', 'image/png'], 
                                 capture_output=True, timeout=2).stdout
            return Image.open(io.BytesIO(data)) if data else None
        except:
            return None
    
    def rich_input(prompt=""):
        def paste(b, c): 
            img = get_clipboard_image()
            if img:
                for ch in f"[IMAGE:{img.size[0]}x{img.size[1]}]": 
                    b.insert(c, ch)
                    c += 1
            else:
                try:
                    for ch in subprocess.run(['wl-paste'], capture_output=True, text=True, timeout=1).stdout: 
                        b.insert(c, ch)
                        c += 1
                except: 
                    pass
            return b, c
        
        cb = {
            'ctrl_c': lambda b,c: (b,c,True),
            'ctrl_v': lambda b,c: (*paste(b,c),False),
            'enter': lambda b,c: (b[:c]+['\n']+b[c:],c+1,False),
            'backspace': lambda b,c: (b[:c-1]+b[c:],c-1,False) if c>0 else (b,c,False),
            'left': lambda b,c: (b,max(0,c-1),False),
            'right': lambda b,c: (b,min(len(b),c+1),False),
            'esc_enter': lambda b,c: (b,c,True),
            'char': lambda b,c,ch: (b[:c]+[ch]+b[c:],c+1,False),
        }
        
        print(prompt, end='', flush=True)
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            buf, cur = [], 0
            while True:
                ch = sys.stdin.read(1)
                redraw = True
                if ch == '\x03': 
                    raise KeyboardInterrupt
                elif ch == '\x16': 
                    buf,cur,exit = cb['ctrl_v'](buf,cur)
                elif ch in ('\r','\n'): 
                    buf,cur,exit = cb['enter'](buf,cur)
                    redraw=False
                    print('\r\n',end='',flush=True)
                elif ch in ('\x7f','\x08'): 
                    buf,cur,exit = cb['backspace'](buf,cur)
                elif ch == '\x1b':
                    n = sys.stdin.read(1)
                    if n in ('\r','\n'): 
                        print('\r\n')
                        return ''.join(buf)
                    elif n == '[':
                        n2 = sys.stdin.read(1)
                        if n2 == 'D': 
                            buf,cur,exit = cb['left'](buf,cur)
                        elif n2 == 'C': 
                            buf,cur,exit = cb['right'](buf,cur)
                elif ch.isprintable() or ch == ' ': 
                    buf,cur,exit = cb['char'](buf,cur,ch)
                else: 
                    redraw = False
                if redraw:
                    s=cur
                    while s>0 and buf[s-1]!='\n': s-=1
                    e=cur
                    while e<len(buf) and buf[e]!='\n': e+=1
                    sys.stdout.write('\r\033[K'+''.join(buf[s:e])+'\r'+(f'\033[{cur-s}C' if cur>s else ''))
                    sys.stdout.flush()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    
    def process_mathpix_image(img):
        if not KEY_MATHPIX_ID:
            return "[Mathpix not configured]"
        
        temp_path = Path("temp_clipboard_image.png")
        img.save(temp_path)
        
        try:
            headers = {
                "app_id": KEY_MATHPIX_ID,
                "app_key": KEY_MATHPIX_KEY
            }
            
            with open(temp_path, 'rb') as f:
                files = {'file': f}
                options = {'formats': ['text']}
                form_data = {'options_json': json.dumps(options)}
                
                response = requests.post(
                    "https://api.mathpix.com/v3/text",
                    headers=headers,
                    files=files,
                    data=form_data
                )
            
            response.raise_for_status()
            result = response.json()
            extracted_text = result.get('text', '[Failed to extract text]')
            
            temp_path.unlink()
            return extracted_text
            
        except Exception as e:
            logger.error(f"Mathpix API error: {str(e)}")
            if temp_path.exists():
                temp_path.unlink()
            return f"[Image processing error: {str(e)}]"
    
    def process_user_input(user_input):
        image_pattern = r'\[IMAGE:(\d+)x(\d+)\]'
        matches = list(re.finditer(image_pattern, user_input))
        
        if not matches:
            return user_input
        
        logger.info(f"Found {len(matches)} image markers")
        processed_input = user_input
        offset = 0
        
        for match in matches:
            print(f"{Fore.YELLOW}Processing image from clipboard...{Style.RESET_ALL}")
            
            img = get_clipboard_image()
            if img:
                print(f"{Fore.YELLOW}Sending to Mathpix...{Style.RESET_ALL}")
                extracted_text = process_mathpix_image(img)
                
                print(f"{Fore.GREEN}Image processed{Style.RESET_ALL}")
                print(f"{Fore.CYAN}Extracted:{Style.RESET_ALL}")
                print_colored(extracted_text[:200] + "..." if len(extracted_text) > 200 else extracted_text, Fore.LIGHTBLUE_EX)
                
                replacement = f"\n[IMAGE CONTENT]:\n{extracted_text}\n[END IMAGE]\n"
            else:
                replacement = "[No image in clipboard]"
            
            start = match.start() + offset
            end = match.end() + offset
            processed_input = processed_input[:start] + replacement + processed_input[end:]
            offset += len(replacement) - (end - start)
        
        return processed_input
    
    prompt_text = read_file("src/assets/prompt.txt")
    context_text = read_file("context.txt")
    
    if not prompt_text:
        print(f"{Fore.RED}Error: prompt.txt not found{Style.RESET_ALL}")
        return
    
    client = anthropic.Anthropic(api_key=KEY_CLAUDE)
    conversation = []
    logger.info("Chat initialized")
    
    context_mode = "1M tokens" if USE_1M_CONTEXT else "200K tokens"
    print(f"{Fore.CYAN}{'='*60}")
    print(f"{Fore.CYAN}AI Code Assistant Started ({context_mode})")
    print(f"{Fore.CYAN}Press Ctrl+V to paste images, Esc+Enter to submit")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
    
    task_input = rich_input(f"{Fore.GREEN}Enter your task: {Style.RESET_ALL}")
    task = process_user_input(task_input)
    logger.info(f"User task: {task[:100]}...")
    
    first_message = f"{prompt_text}\n\nCONTEXT:\n{context_text}\n\nTASK:\n{task}"
    
    while True:
        print(f"\n{Fore.YELLOW}Sending request to AI...{Style.RESET_ALL}\n")
        logger.info("Sending request to AI")
        
        conversation.append({
            "role": "user",
            "content": first_message if 'first_message' in locals() else task
        })
        
        if 'first_message' in locals():
            del first_message
        
        stream_kwargs = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 32000,
            "messages": conversation
        }
        
        if USE_1M_CONTEXT:
            stream_kwargs["betas"] = ["context-1m-2025-08-07"]
            logger.info("Using 1M token context window")
        
        with client.messages.stream(**stream_kwargs) as stream:
            response_text = ""
            for text in stream.text_stream:
                print(text, end="", flush=True)
                response_text += text
        
        print()
        conversation.append({
            "role": "assistant",
            "content": response_text
        })
        
        logger.info(f"Received response (length: {len(response_text)})")
        
        code_blocks = extract_code_blocks(response_text)
        
        if code_blocks:
            for idx, code in enumerate(code_blocks, 1):
                print(f"\n{Fore.CYAN}{'='*60}")
                print(f"{Fore.CYAN}EXECUTING CODE BLOCK {idx}/{len(code_blocks)}")
                print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
                
                logger.info(f"Executing code block {idx}")
                
                try:
                    output = execute_python_code(code)
                    logger.info(f"Code execution completed for block {idx}")
                    
                    print(f"{Fore.GREEN}{'='*60}")
                    print(f"{Fore.GREEN}CODE OUTPUT:")
                    print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
                    print_colored(output, Fore.LIGHTBLUE_EX)
                    print()
                    
                    task = f"Code execution output:\n{output}"
                    
                except Exception as e:
                    logger.error(f"Code execution failed: {str(e)}")
                    error_msg = f"Error executing code: {str(e)}"
                    print(f"{Fore.RED}{error_msg}{Style.RESET_ALL}\n")
                    task = error_msg
            
            continue
        
        cmd = extract_command_block(response_text)
        
        if cmd == "DONE":
            print(f"\n{Fore.GREEN}{'='*60}")
            print(f"{Fore.GREEN}Task completed!")
            print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}\n")
            logger.info("Task marked as DONE")
            
            new_task_input = rich_input(f"{Fore.GREEN}Enter new task (or Esc+Enter to exit): {Style.RESET_ALL}")
            if not new_task_input or not new_task_input.strip():
                logger.info("User exited")
                break
            task = process_user_input(new_task_input)
            logger.info(f"New task: {task[:100]}...")
        
        elif cmd == "AWAIT":
            print(f"\n{Fore.YELLOW}AI is waiting for input{Style.RESET_ALL}")
            user_input_raw = rich_input(f"{Fore.GREEN}Enter info: {Style.RESET_ALL}")
            task = process_user_input(user_input_raw)
            logger.info(f"User provided: {task[:100]}...")
        else:
            break

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Fore.RED}Interrupted{Style.RESET_ALL}")
    except Exception as e:
        print(f"\n{Fore.RED}Fatal error: {str(e)}{Style.RESET_ALL}")