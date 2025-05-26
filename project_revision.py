import asyncio
import json
import logging
import random
import string
from typing import Any, Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def generate_site_id(length: int = 17) -> str:
    """Generate a random alphanumeric site ID of given length."""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


class ProjectRevisionError(Exception):
    """Custom exception for project revision failures."""
    pass


async def process_project_revision(
    project_id: str,
    prompt: str,
    *,
    model_id: str = "gemini-flash",
    base_url: str = "https://websim.com",
    cookies: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    session_cookies = cookies or {}
    #print(session_cookies)
    headers = {'Content-Type': 'application/json'}

    async with aiohttp.ClientSession(cookies=session_cookies) as session:
        # 1) Fetch current project info
        url_proj = f"{base_url}/api/v1/projects/{project_id}"
        async with session.get(url_proj, headers=headers) as resp:
            if resp.status != 200:
                body = await resp.text()
                msg = f"Failed to fetch project info: {resp.status}, Response: {body}"
                logger.error(msg)
                raise ProjectRevisionError(msg)
            proj_data = await resp.json()
            parent_version = proj_data['project_revision']['version']
            logger.info(f"Current project version: {parent_version}")

        # 2) Create new revision
        url_rev = f"{base_url}/api/v1/projects/{project_id}/revisions"
        payload_rev = {'parent_version': parent_version}

        async with session.post(url_rev, headers=headers, json=payload_rev) as resp:
            if resp.status != 201:
                body = await resp.text()
                msg = f"Failed to create revision: {resp.status}, Response: {body}"
                logger.error(msg)
                raise ProjectRevisionError(msg)
            rev_data = await resp.json()
            #pprint.pp(rev_data,depth=3)
            #pprint.pp(dict(resp.headers),depth=3)
            rev_id = rev_data['project_revision']['id']
            rev_version = rev_data['project_revision']['version']
            logger.info(f"Created revision ID: {rev_id}, Version: {rev_version}")
        
        # 3) Create draft site
        site_id = generate_site_id()
        logger.info(f"Generated site ID: {site_id}")
        url_site = f"{base_url}/api/v1/sites"
        # Extra Step: Enable optional features
        enableMultiplayer = "multiplayer" in prompt.lower()
        enableDB = "database" in prompt.lower() or "db" in prompt.lower()

        #Construct Final Payload
        payload_site = {
            'generate': {
                'prompt': {
                    'type': 'plaintext',
                    'text': prompt,
                    'data': None
                },
                'flags': {'use_worker_generation': False},
                'model': model_id,
                'lore': {
                    'version': 1,
                    'attachments': [],
                    'references': [],
                    'enableDatabase': False,
                    'enableApi': True,
                    'enableMultiplayer': enableMultiplayer,
                    'enableMobilePrompt': True,
                    'enableDB': enableDB,
                    'enableLLM': False,
                    'enableLLM2': True,
                    'enableTweaks': False,
                    'features': {
                        'context': True,
                        'errors': True,
                        'htmx': True,
                        'images': True,
                        'navigation': True
                    }
                }
            },
            'project_id': project_id,
            'project_version': rev_version,
            'project_revision_id': rev_id,
            'site_id': site_id
        }
        async with session.post(url_site, headers=headers, json=payload_site) as resp:
            if resp.status != 201:
                body = await resp.text()
                msg = f"Failed to create site: {resp.status}, Response: {body}"
                logger.error(msg)
                raise ProjectRevisionError(msg)
            logger.info("Created draft site successfully")

        # 4) Confirm draft
        url_confirm = f"{base_url}/api/v1/projects/{project_id}/revisions/{rev_version}"
        async with session.patch(url_confirm, headers=headers, json={'draft': False}) as resp:
            if resp.status != 200:
                body = await resp.text()
                msg = f"Failed to confirm draft: {resp.status}, Response: {body}"
                logger.error(msg)
                raise ProjectRevisionError(msg)
            logger.info("Confirmed draft successfully")

        # 5) Update project current version
        url_update = f"{base_url}/api/v1/projects/{project_id}"
        async with session.patch(url_update, headers=headers, json={'current_version': rev_version}) as resp:
            if resp.status != 200:
                body = await resp.text()
                msg = f"Failed to update current version: {resp.status}, Response: {body}"
                logger.error(msg)
                raise ProjectRevisionError(msg)
            logger.info(f"Updated project current version to: {rev_version}")

        return {
            'success': True,
            'revision_id': rev_id,
            'version': rev_version,
            'site_id': site_id
        }



def create_revision(
    project_id: str,
    prompt: str,
    *,
    model_id: str = "gemini-flash",
    base_url: str = "https://websim.com",
    cookies: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Synchronous helper to run process_project_revision from non-async code.
    """
    if not project_id or not prompt:
        logger.error('Usage: create_revision(project_id, "prompt text")')
        return {}

    logger.info(f"Creating revision for project: {project_id}")
    return asyncio.run(process_project_revision(
        project_id,
        prompt,
        base_url=base_url,
        cookies=cookies
    ))


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print('Usage: python project_revision.py <project_id> "<prompt text>"')
        sys.exit(1)

    proj, prm = sys.argv[1], sys.argv[2]
    result = create_revision(proj, prm)
    print(json.dumps(result, indent=2))
