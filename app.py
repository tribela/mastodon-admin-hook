from typing import Dict, List, Literal, Optional

import fastapi
import httpx


from pydantic import BaseModel

app = fastapi.FastAPI()

INSTANCE_URL = "https://qdon.space"


class Account(BaseModel):
    username: str
    domain: Optional[str] = None
    ...


class Rule(BaseModel):
    id: str
    text: str


class ReportObject(BaseModel):
    id: int
    account: Account
    target_account: Account
    statuses: List[Dict]
    comment: Optional[str]
    created_at: str
    updated_at: str
    forwarded: Optional[bool]
    category: str
    rules: List[Rule]


class Report(BaseModel):
    event: Literal['report.created']
    created_at: str
    object: ReportObject


def pretty_username(account: Account) -> str:
    if account.domain is None:
        return account.username
    return f'{account.username}@{account.domain}'


@app.post("/hooks/{hook_id}/{hook_token}")
async def hook(hook_id: str, hook_token: str, hook_object: Report):
    if hook_object.event != 'report.created':
        return fastapi.Response(status_code=400)

    async with httpx.AsyncClient() as client:
        obj = hook_object.object
        category = obj.category

        account_username = pretty_username(obj.account)
        target_account_username = pretty_username(obj.target_account)

        # Note that empty string causes an error in Discord
        violated_rules = '\n'.join(
            f'- {rule.text}'
            for rule in obj.rules
        ) or 'None'

        comment = obj.comment

        attached_statuses_count = len(obj.statuses)

        url = f"{INSTANCE_URL}/admin/reports/{obj.id}"
        content = f"@here are new report from qdon.space!\n{url}"

        body = {
            "username": "Report reporter",
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
                        "name": "Attached statuses",
                        "value": attached_statuses_count,
                        "inline": True,
                    },
                    {
                        "name": "Forwarded",
                        "value": "yes" if obj.forwarded else "no",
                        "inline": True,
                    },
                    {
                        "name": "Rules",
                        "value": violated_rules,
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
            print(hook_object)
            print(body)
            print(res.json())

    return fastapi.Response(status_code=201)
