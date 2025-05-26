import asyncio
import logging
from typing import Optional, Dict
import aiohttp
import yaml
import os
from http.cookies import SimpleCookie

from project_revision import process_project_revision

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("monitor")

def load_config(config_path: str = "config.yaml") -> Dict:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    if 'cookies' in config and isinstance(config['cookies'], str):
        cookie = SimpleCookie()
        cookie.load(config['cookies'])
        config['cookies'] = {k: v.value for k, v in cookie.items()}
    return config


async def check_and_respond(project_id:str,config:dict):
    try:
        #Load Config Items
        project_id = config.get('project_id')
        base_url = config.get('base_url', 'http://localhost')
        model_id = config.get('model_id','gemini-flash')
        additional_note = config.get('additional_note','')
        cookies = config.get('cookies',{})
        #Logical Switches
        require_like_project = config.get('require_like_project',False)

        #text to check for and send
        loc_auto_response_create_revision = config.get('auto_response_prefix') + config.get('auto_response_create_revision')
        loc_auto_response_require_likes = config.get('auto_response_prefix') + config.get('auto_response_require_likes')
        loc_auto_response_prefix = config.get('auto_response_prefix')



        logger.info(f"[Monitor] Checking project {project_id}")
        headers = {'Content-Type': 'application/json'}

        async with aiohttp.ClientSession(cookies=cookies) as session:
            # Step 1: Fetch latest revisions
            url_revisions = f"{base_url}/api/v1/projects/{project_id}/revisions"
            async with session.get(url_revisions) as resp:
                if resp.status != 200:
                    logger.error(f"Fetch revisions failed: {resp.status}, Body: {await resp.text()}")
                    return
                rev_data = await resp.json()
                first = rev_data['revisions']['data'][0] if rev_data['revisions']['data'] else None
                if not first:
                    logger.info("[Monitor] No revisions found")
                    return
                logger.info(f"[Monitor] site.state = {first['site']['state']}")
                if first['site']['state'] != 'done':
                    logger.info("[Monitor] Site not yet ready. Retrying in 10s.")
                    return
                owner_id = first['project_revision']['created_by']['id']

            # Step 2: Fetch comments
            url_comments = f"{base_url}/api/v1/projects/{project_id}/comments"
            async with session.get(url_comments) as resp:
                if resp.status != 200:
                    logger.error(f"Fetch comments failed: {resp.status}, Body: {await resp.text()}")
                    return
                comm_data = await resp.json()
                entry = comm_data['comments']['data'][0] if comm_data['comments']['data'] else None
                if not entry:
                    logger.info("[Monitor] No comments to process")
                    return
                comment = entry['comment']
                comment_id = comment['id']
                raw_content = comment['raw_content']
                author = comment['author']
                logger.info(f"[Monitor] First comment by {author['username']}: \"{raw_content}\"")

            # Step 3: Check replies for existing auto response
            url_replies = f"{base_url}/api/v1/projects/{project_id}/comments/{comment_id}/replies"
            async with session.get(url_replies) as resp:
                if resp.status != 200:
                    logger.error(f"Fetch replies failed: {resp.status}, Body: {await resp.text()}")
                    return
                rep_data = await resp.json()
                already_replied = any(
                    r['comment']['author']['id'] == owner_id and
                    loc_auto_response_prefix in r['comment']['raw_content']
                    for r in rep_data['comments']['data']
                )
                if already_replied:
                    logger.info("[Monitor] Owner already replied automatically. Skipping.")
                    return

            # Step 4: Check if author has liked the project if required
            # Going through the pages is usually not required
            if require_like_project:
                url_likes = f"{base_url}/api/v1/users/{author['username']}/likes"
                async with session.get(url_likes) as resp:
                    if resp.status != 200:
                        logger.error(f"Fetch likes failed: {resp.status}, Body: {await resp.text()}")
                        return
                    like_data = await resp.json()
                    has_liked = any(l['project']['id'] == project_id for l in like_data['likes']['data'])
                    if not has_liked:
                        logger.info("[Monitor] Author has not liked the project. Sending reminder.")
                        await session.post(
                            url_comments,
                            headers=headers,
                            json={
                                'content': loc_auto_response_require_likes,
                                'parent_comment_id': comment_id
                            }
                        )
                        logger.info("[Monitor] Like-reminder posted.")
                        return
            else:
                logger.info("[Monitor] Checking likes not required.")

            # Step 5: Create new revision with safety note
            logger.info("[Monitor] Creating new revision...")
            revision = await process_project_revision(
                project_id,
                raw_content + additional_note,
                model_id=model_id,
                base_url=base_url,
                cookies=cookies
            )
            logger.info(f"[Monitor] Revision created: ID={revision['revision_id']}, version={revision['version']}")

            # Step 6: Post confirmation comment
            await session.post(
                url_comments,
                headers=headers,
                json={
                    'content': loc_auto_response_create_revision,
                    'parent_comment_id': comment_id
                }
            )
            logger.info("[Monitor] Confirmation comment posted.")

    except Exception as e:
        logger.error(f"[Monitor] Error: {e}")


def monitor_project(config: dict, *, interval_sec: int = 10, **kwargs):
    project_id = config.get('project_id')
    async def runner():
        while True:
            await check_and_respond(project_id, config)
            await asyncio.sleep(interval_sec)

    logger.info(f"[Monitor] Starting automatic monitor for project {project_id}")
    asyncio.run(runner())

if __name__ == '__main__':
    config = load_config()
    monitor_project(config,interval_sec=config.get('interval',10))
