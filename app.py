from typing import Dict, List, Literal, Optional

import re

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


class Account(BaseModel):
    id: int
    username: str
    acct: str
    url: str
    display_name: str
    note: str
    avatar: str
    avatar_static: str
    header: str
    header_static: str
    locked: str
    # fields: List[Field]
    # emojis
    bot: bool
    ...


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
    account: Account
    invited_by_account_id: Optional[int] = None
    ...


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
    warnings = []
    HANGUL_RE = re.compile(r'[ㄱ-ㅎㅏ-ㅣ가-힣]')

    async with httpx.AsyncClient() as client:
        if account.ip:
            country = (await client.get(f'https://ifconfig.co/country?ip={account.ip}')).text.strip()

            # Check spam DB
            spam_db_res = await client.get(f'https://api.spamdb.net/v1/ip/{account.ip}')
        else:
            country = 'Unknown'

        if account.locale != 'ko' or \
                HANGUL_RE.search(account.account.display_name) is None or \
                HANGUL_RE.search(account.account.note) is None:
            warnings.append('한국인이 아닌 것 같습니다.')

        if country != 'South Korea':
            warnings.append('가입 IP가 한국이 아닙니다.')

        # If there are warnings, send a message to Discord
        if warnings:
            warning_text = '\n'.join(
                f'- {warn}'
                for warn in warnings
            ) or 'None'

            body = {
                "username": "Account reporter",
                "content": "New account approved!",
                "embeds": [{
                    "title": "New account",
                    "color": 0xff8b13,
                    "fields": [
                        {
                            "name": "Username",
                            "value": account.account.username,
                            "inline": True,
                        },
                        {
                            "name": "Display name",
                            "value": account.account.display_name,
                            "inline": True,
                        },
                        {
                            "name": "Bot",
                            "value": str(account.account.bot),
                            "inline": True,
                        },
                        {
                            "name": "Warning",
                            "value": warning_text,
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
                print(account)
                print(body)
                print(res.json())

    return fastapi.Response(status_code=201)
