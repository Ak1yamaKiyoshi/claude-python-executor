import logging
import logging.config
import yaml
from pathlib import Path

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the specified name"""
    config_path = Path(__file__).parent / "logger_config.yaml"
    
    if config_path.exists():
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            logging.config.dictConfig(config)
    else:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    return logging.getLogger(name)