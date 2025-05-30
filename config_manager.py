from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
import os
from typing import Optional, Dict
from http.cookies import SimpleCookie

yaml = YAML()
yaml.preserve_quotes = True

def load_config(config_path: str = "config.yaml") -> Dict:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found when trying to load config: {config_path}")
    with open(config_path, 'r') as f:
        config = yaml.load(f)
    if 'cookies' in config and isinstance(config['cookies'], str):
        cookie = SimpleCookie()
        cookie.load(config['cookies'])
        config['cookies'] = {k: v.value for k, v in cookie.items()}
    return config

def update_config(config: CommentedMap, config_path: str = "config.yaml"):
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found when trying to update config: {config_path}")
    with open(config_path, "w") as f:
        yaml.dump(config, f)