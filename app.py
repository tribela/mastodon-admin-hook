from typing import Dict, List, Literal, Optional

import fastapi
import httpx


from pydantic import BaseModel

app = fastapi.FastAPI()

INSTANCE_URL = "https://qdon.space"


# For ReportObject
class AdminAccount(BaseModel):
    username: str
    domain: Optional[str] = None
    ...


class Rule(BaseModel):
    id: str
    text: str


class ReportObject(BaseModel):
    id: int
    account: AdminAccount
    target_account: AdminAccount
    statuses: List[Dict]
    comment: Optional[str]
    created_at: str
    updated_at: str
    forwarded: Optional[bool]
    category: str
    rules: List[Rule]


# For AdminAccountObject
class Ip(BaseModel):
    ip: str
    used_at: str


class AdminAccountObject(BaseModel):
    id: int
    username: str
    domain: Optional[str] = None
    created_at: str
    email: str
    ip: Optional[str] = None
    ips: List[Ip]
    locale: str
    invite_request: Optional[str] = None
    confirmed: bool
    approved: bool
    disabled: bool
    silenced: bool
    suspended: bool
    invited_by_account_id: Optional[int] = None


class WebHook(BaseModel):
    event: Literal['report.created'] | Literal['account.approved'] | Literal['account.created']
    created_at: str
    object: ReportObject


def pretty_username(account: AdminAccount) -> str:
    if account.domain is None:
        return account.username
    return f'{account.username}@{account.domain}'


@app.post("/hooks/{hook_id}/{hook_token}")
async def hook(hook_id: str, hook_token: str, hook_object: WebHook):

    if hook_object.event == 'report.created':
        return await handle_report_created(hook_id, hook_token, hook_object.object)
    elif hook_object.event == 'account.approved':
        return await handle_account_approved(hook_id, hook_token, hook_object.object)
    else:
        return fastapi.Response(status_code=400)


async def handle_report_created(hook_id: str, hook_token: str, report: ReportObject):

    async with httpx.AsyncClient() as client:
        category = report.category

        account_username = pretty_username(report.account)
        target_account_username = pretty_username(report.target_account)

        # Note that empty string causes an error in Discord
        violated_rules = '\n'.join(
            f'- {rule.text}'
            for rule in report.rules
        ) or 'None'

        comment = report.comment

        attached_statuses_count = len(report.statuses)

        url = f"{INSTANCE_URL}/admin/reports/{report.id}"
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
                        "value": "yes" if report.forwarded else "no",
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
            print(report)
            print(body)
            print(res.json())

    return fastapi.Response(status_code=201)


async def handle_account_approved(hook_id: str, hook_token: str, account: AdminAccountObject):
    return fastapi.Response(status_code=201)
