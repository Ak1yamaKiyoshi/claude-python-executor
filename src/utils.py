
from src.logger import get_logger
logger = get_logger(__name__)


def read_file(filepath):
    logger.info(f"Reading file: {filepath}")
    try:
        with open(filepath, 'r') as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"File not found: {filepath}")
        return ""

def extract_code_blocks(text):
    pattern = r'```python\n(.*?)```'
    matches = re.findall(pattern, text, re.DOTALL)
    logger.info(f"Extracted {len(matches)} Python code blocks")
    return matches

def extract_command_block(text):
    inline_pattern = r'\[(DONE|AWAIT)\]'
    inline_match = re.search(inline_pattern, text)
    if inline_match:
        cmd = inline_match.group(1)
        logger.info(f"Extracted inline command: {cmd}")
        return cmd
    
    block_pattern = r'```cmd\n(.*?)```'
    block_match = re.search(block_pattern, text, re.DOTALL)
    if block_match:
        cmd = block_match.group(1).strip()
        logger.info(f"Extracted command block: {cmd}")
        return cmd
    
    return None

def print_colored(text, color, prefix=""):
    lines = text.split('\n')
    for line in lines:
        print(f"{color}{prefix}{line}{Style.RESET_ALL}")
