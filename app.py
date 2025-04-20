from typing import Dict, List, Literal, Optional

import re

import asyncwhois
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


class AccountField(BaseModel):
    name: str
    value: str
    verified_at: Optional[str]


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
    fields: List[AccountField]
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
    event: Literal['report.created'] | Literal['account.approved'] | Literal['account.created'] | Literal['status.created']
    created_at: str
    object: ReportObject | AdminAccountObject


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
    elif hook_object.event == 'status.created':
        return await handle_status_created(hook_id, hook_token, hook_object.object)
    else:
        print(f'Unprocessible event: {hook_object.event}')
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

        color = 0xff0000

        to_remote = report.target_account.domain is not None
        from_remote = report.account.domain is not None

        # Silent if remote spam
        if report.category == 'spam' and to_remote:
            content = f'@silent {content}'
            color = 0xffd700  # mustard

        if from_remote:
            forwarded = 'From remote'
        elif to_remote:
            forwarded = 'To remote' if report.forwarded else 'Not forwarded'
        else:
            forwarded = 'N/A'

        body = {
            "username": "Report reporter",
            "content": content,
            "embeds": [{
                "title": "New report",
                "description": comment if comment else "No comment",
                "color": color,
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
                        "value": forwarded,
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


async def handle_account_approved(hook_id: str, hook_token: str, admin_account: AdminAccountObject):
    warnings = []
    HANGUL_RE = re.compile(r'[ㄱ-ㅎㅏ-ㅣ가-힣]')

    async with httpx.AsyncClient() as client:
        try:
            rawstr, whois_dict = await asyncwhois.aio_whois(admin_account.ip)
            country = whois_dict.get('country')
            if country is None:
                if matched := re.search(r'^country:\s*([A-Z]{2})$', rawstr, re.MULTILINE | re.IGNORECASE):
                    country = matched.group(1)
                else:
                    country = 'Unknown'
        except Exception as e:
            print(f'Error while checking IP for {admin_account.ip}, {e}')
            country = 'Unknown'

        if country != 'KR':
            warnings.append(f'가입 IP가 한국이 아닙니다. ({country})')

        if admin_account.locale != 'ko':
            warnings.append(f'언어 설정이 한국어가 아닙니다. ({admin_account.locale})')

        possible_fields = list(filter(lambda x: x is not None, [
            admin_account.account.display_name,
            admin_account.account.note,
            *[field.name + field.value for field in admin_account.account.fields],
        ]))

        if possible_fields and not any((HANGUL_RE.search(field) for field in possible_fields)):
            warnings.append('프로필에 한글이 없습니다.')

        email_domain = admin_account.email.split('@')[-1]
        try:
            mx_res = await client.get(f'https://api.usercheck.com/domain/{email_domain}')
            mx_res.raise_for_status()
            if mx_res.json()['disposable']:
                warnings.append('일회용 이메일을 사용하고 있습니다.')
        except Exception as e:
            print(f'Error while checking MX record for {email_domain}, {e}')

        # If there are no warnings, we don't need to send a message
        if not warnings:
            return fastapi.Response(status_code=201)

        warning_text = '\n'.join(
            f'- {warn}'
            for warn in warnings
        ) or 'None'

        body = {
            "username": "Account reporter",
            "content": f"New account approved!\n{INSTANCE_URL}/admin/accounts/{admin_account.id}",
            "embeds": [{
                "title": "New account",
                "color": 0xff8b13,
                "fields": [
                    {
                        "name": "Username",
                        "value": admin_account.account.username,
                        "inline": True,
                    },
                    {
                        "name": "Display name",
                        "value": admin_account.account.display_name,
                        "inline": True,
                    },
                    {
                        "name": "Email",
                        "value": admin_account.email,
                        "inline": True,
                    },
                    {
                        "name": "IP",
                        "value": admin_account.ip,
                        "inline": True,
                    },
                    {
                        "name": "Bot",
                        "value": str(admin_account.account.bot),
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
            print(admin_account)
            print(body)
            print(res.json())

    return fastapi.Response(status_code=201)


async def handle_status_created(hook_id: str, hook_token: str, status):
    text = status.text
    print(text)
