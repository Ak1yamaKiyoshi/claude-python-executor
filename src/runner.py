import subprocess
import sys
import shutil
import re
from pathlib import Path
from src.logger import get_logger

logger = get_logger(__name__)

def check_or_create_venv():
    venv_path = Path(".env")
    if not venv_path.exists():
        logger.info("Creating virtual environment")
        subprocess.run(
            [sys.executable, "-m", "venv", ".env"], 
            check=True,
            capture_output=True
        )
        logger.info("Virtual environment created")
    else:
        logger.info("Virtual environment exists")
    return venv_path

def get_venv_python():
    return Path(".env/bin/python")

def get_venv_pip():
    return Path(".env/bin/pip")

def extract_pip_packages(content):
    packages = []
    pattern = r'#\s*pip install\s+([^\n]+)'
    matches = re.findall(pattern, content)
    for match in matches:
        packages.extend(match.strip().split())
    logger.info(f"Extracted packages: {packages}")
    return packages

def check_and_install_packages(packages):
    pip_exe = get_venv_pip()
    
    for package in packages:
        logger.info(f"Checking package: {package}")
        check = subprocess.run(
            [str(pip_exe), "show", package],
            capture_output=True,
            text=True
        )
        
        if check.returncode != 0:
            logger.info(f"Installing package: {package}")
            subprocess.run(
                [str(pip_exe), "install", package],
                check=True,
                capture_output=True
            )
            logger.info(f"Package installed: {package}")
        else:
            logger.info(f"Package already installed: {package}")

def execute_python_code(code: str) -> str:
    logger.info("Starting execution pipeline")
    
    logger.info("Step 1: Checking virtual environment")
    check_or_create_venv()
    
    logger.info("Step 2: Creating execution directory")
    exec_dir = Path("executed_environment")
    exec_dir.mkdir(exist_ok=True)
    logger.info(f"Execution directory created: {exec_dir}")
    
    logger.info("Step 3: Writing code to main.py")
    main_py = exec_dir / "main.py"
    with open(main_py, "w") as f:
        f.write(code)
    logger.info(f"Code written to: {main_py}")
    
    logger.info("Step 4: Extracting dependencies")
    packages = extract_pip_packages(code)
    
    if packages:
        logger.info("Step 5: Installing dependencies")
        check_and_install_packages(packages)
    else:
        logger.info("Step 5: No dependencies to install")
    
    logger.info("Step 6: Executing main.py")
    python_exe = get_venv_python()
    result = subprocess.run(
        [str(python_exe), str(main_py)],
        capture_output=True,
        text=True
    )
    logger.info(f"Execution completed with exit code: {result.returncode}")
    
    logger.info("Step 7: Cleaning up")
    shutil.rmtree(exec_dir)
    logger.info("Execution directory deleted")
    
    logger.info("Execution pipeline finished")
    
    output = f"""{'='*50}
OUTPUT:
{'='*50}
{result.stdout if result.stdout else '(no stdout)'}
{'ERRORS:' if result.stderr else ''}
{result.stderr if result.stderr else ''}
{'='*50}
Exit code: {result.returncode}"""
    
    return output

def main():
    logger.info("Reading buffer.txt")
    with open("buffer.txt", "r") as f:
        code = f.read()
    logger.info("Buffer.txt loaded")
    
    output = execute_python_code(code)
    print(output)

if __name__ == "__main__":
    main()