import logging
from typing import Dict, Optional
import aiohttp
from http.cookies import SimpleCookie
import yaml
import os

from config_manager import load_config,update_config

logger = logging.getLogger("cookie_manager")

CONFIG_PATH = "config.yaml"

async def refresh_cookies(base_url: str, current_cookies: Dict[str, str]) -> Optional[Dict[str, str]]:
    """
    Makes a GET request to base_url and refreshes cookies if the server returns Set-Cookie headers.
    Updates both in-memory cookies and config.yaml.
    """
    try:
        logger.info("[CookieManager] Attempting to refresh cookies from base URL...")
        async with aiohttp.ClientSession() as session:
            async with session.get(base_url, cookies=current_cookies) as resp:
                if resp.status != 200:
                    logger.error(f"[CookieManager] Failed to refresh cookies: status {resp.status}")
                    return None

                set_cookie_headers = resp.headers.getall("Set-Cookie", [])
                if not set_cookie_headers:
                    logger.warning("[CookieManager] No Set-Cookie headers found in response.")
                    return None

                new_cookies = {}
                for header in set_cookie_headers:
                    sc = SimpleCookie()
                    sc.load(header)
                    for k, v in sc.items():
                        new_cookies[k] = v.value
                        logger.info(f"[CookieManager] Refreshed cookie: {k}={v.value}")

                # Update config.yaml
                save_cookies_to_config(new_cookies)
                return new_cookies

    except Exception as e:
        logger.error(f"[CookieManager] Error refreshing cookies: {e}")
        return None

def save_cookies_to_config(new_cookies: Dict[str, str]):
    try:
        config = load_config()
        cookie_string = "; ".join(f"{k}={v}" for k, v in new_cookies.items())
        config['cookies'] = cookie_string
        update_config(config)
        logger.info("[CookieManager] Updated cookies in config.yaml")
    except Exception as e:
        logger.error(f"[CookieManager] Failed to update config.yaml: {e}")

def is_jwt_expired(resp_json: dict) -> bool:
    return (
        isinstance(resp_json, dict)
        and resp_json.get("error", {}).get("name","") == "ResponseError"
        and resp_json["error"].get("cause",{}).get("message","") == "JWT expired"
    )
