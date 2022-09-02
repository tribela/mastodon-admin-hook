from typing import Literal

import fastapi
import httpx

from pydantic import BaseModel
from typing import Dict, List, Optional

app = fastapi.FastAPI()

INSTANCE_URL = "https://qdon.space"


class ReportObject(BaseModel):
    id: int
    account_id: int
    target_account_id: int
    status_ids: Optional[List[int]]
    comment: Optional[str]
    created_at: str
    updated_at: str
    forwarded: Optional[bool]
    category: str
    rule_ids: Optional[List[int]]


class Report(BaseModel):
    type: Literal['report.created']
    created_at: str
    object: ReportObject


avatar_url = httpx.get(f'{INSTANCE_URL}/api/v1/accounts/1').json()['avatar']


@app.post("/hooks/<hook_id>/<hook_token>")
async def hook(hook_id: str, hook_token: str, hook_object: Report):

    if hook_object.type != 'report.created':
        return fastapi.Response(status_code=400)

    async with httpx.AsyncClient() as client:
        obj = hook_object.object
        account_id = obj.account_id
        target_account_id = obj.target_account_id
        category = obj.category
        if obj.rule_ids:
            instance_rules = (await client.get(f'{INSTANCE_URL}/api/v1/instance')).json()['rules']
            rule_ids = [str(rule_id) for rule_id in obj.rule_ids]
            selected_rules = [rule['text'] for rule in instance_rules if rule['id'] in rule_ids]
        else:
            selected_rules = None

        _account = client.get(f'{INSTANCE_URL}/api/v1/accounts/{account_id}')
        _target_account = client.get(f'{INSTANCE_URL}/api/v1/accounts/{target_account_id}')

        account_username = (await _account).json()['username']
        target_account_username = (await _target_account).json()['username']

        comment = obj.comment

        url = f"{INSTANCE_URL}/admin/reports/{obj.id}"
        content = f"New report from qdon.space!\n{url}"

        body = {
            "username": "Report reporter",
            "avatar_url": avatar_url,
            "content": content,
            "embeds": [{
                "title": "New report",
                "description": comment if comment else "No comment",
                "color": 0xff0000,
                "fields": [
                    {
                        "name": "Reporter",
                        "value": account_username,
                        "inline": True,
                    },
                    {
                        "name": "Target account",
                        "value": target_account_username,
                        "inline": True,
                    },
                    {
                        "name": "Category",
                        "value": category,
                        "inline": True,
                    },
                    {
                        "name": "Forwarded",
                        "value": obj.forwarded,
                        "inline": True,
                    },
                    {
                        "name": "Rules",
                        "value": '\n'.join(selected_rules) if selected_rules else "None",
                        "inline": False,
                    },
                ]
            }]
        }

        res = await client.post(
            f"https://discord.com/api/webhooks/{hook_id}/{hook_token}",
            json=body,
        )

        if res.status_code >= 400:
            print(res.json())

    return fastapi.Response(status_code=201)
