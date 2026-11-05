import os
import logging
import requests
import config
import hashlib
import threading
import time

logger = logging.getLogger("YoBotLinkedIn")

_CACHED_PERSON_URN = None
_CACHED_TOKEN_HASH = None
_drafts = {}
_draft_lock = threading.RLock()

SETUP_MESSAGE = "LinkedIn is not connected yet. Complete the LinkedIn developer app setup and store its access token securely in Render. Never send tokens or passwords in Telegram."

def preview(draft):
    return ("**LinkedIn post preview**\n\n**Visibility: Public**\n\n" + draft["text"] +
            "\n\nReply **publish linkedin** to publish this exact post, or **cancel linkedin**. Nothing has been published yet.")

def handle_post_reply(text):
    choice = text.strip().lower().rstrip('.!')
    if choice not in ("publish linkedin", "cancel linkedin"):
        return None
    if not config.is_admin(config.get_current_user_id()):
        return "LinkedIn is restricted to the bot owner."
    with _draft_lock:
        draft = _drafts.pop(config.get_current_user_id(), None)
    if not draft:
        return "No LinkedIn post is awaiting confirmation. Describe the post first."
    if choice == "cancel linkedin":
        return "LinkedIn draft cancelled. Nothing was published."
    fingerprint = hashlib.sha256(config.LINKEDIN_ACCESS_TOKEN.encode()).hexdigest()
    if draft["expires"] < time.monotonic() or draft["account"] != fingerprint:
        return "That LinkedIn preview expired or the connected account changed. Create a new preview before publishing."
    # Consume confirmation before I/O. An uncertain POST must never auto-retry.
    return _publish_post(draft["text"])

@config.require_admin
def get_author_urn(token: str) -> str:
    global _CACHED_PERSON_URN, _CACHED_TOKEN_HASH
    fingerprint = hashlib.sha256(token.encode()).hexdigest()
    if fingerprint != _CACHED_TOKEN_HASH:
        _CACHED_PERSON_URN, _CACHED_TOKEN_HASH = None, fingerprint
    if config.LINKEDIN_PERSON_URN:
        urn = config.LINKEDIN_PERSON_URN
        if not urn.startswith("urn:li:person:"):
            urn = f"urn:li:person:{urn}"
        return urn

    if _CACHED_PERSON_URN:
        return _CACHED_PERSON_URN

    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Jarvis-Bot"
    }

    # Try modern OpenID Connect userinfo endpoint
    try:
        res = requests.get("https://api.linkedin.com/v2/userinfo", headers=headers, timeout=10)
        if res.status_code == 200:
            sub = res.json().get("sub")
            if sub:
                _CACHED_PERSON_URN = f"urn:li:person:{sub}"
                return _CACHED_PERSON_URN
    except Exception as e:
        logger.debug(f"Userinfo endpoint check failed: {e}")

    # Fallback to legacy v2/me endpoint
    try:
        res = requests.get("https://api.linkedin.com/v2/me", headers=headers, timeout=10)
        if res.status_code == 200:
            person_id = res.json().get("id")
            if person_id:
                _CACHED_PERSON_URN = f"urn:li:person:{person_id}"
                return _CACHED_PERSON_URN
    except Exception as e:
        logger.debug(f"v2/me endpoint check failed: {e}")

    return ""

@config.require_admin
def get_linkedin_profile() -> str:
    """
    Checks connection to LinkedIn and retrieves connected account details.
    """
    token = config.LINKEDIN_ACCESS_TOKEN
    if not token:
        return SETUP_MESSAGE

    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Jarvis-Bot"
    }

    # Check OpenID userinfo
    try:
        res = requests.get("https://api.linkedin.com/v2/userinfo", headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            name = data.get("name", "LinkedIn User")
            email = data.get("email", "Not provided")
            sub = data.get("sub", "")
            return f"✅ LinkedIn Connected!\n• Name: {name}\n• Email: {email}\n• Person ID: {sub}"
        
        # Fallback to v2/me
        res_me = requests.get("https://api.linkedin.com/v2/me", headers=headers, timeout=10)
        if res_me.status_code == 200:
            data = res_me.json()
            fname = data.get("localizedFirstName", "")
            lname = data.get("localizedLastName", "")
            pid = data.get("id", "")
            return f"✅ LinkedIn Connected!\n• Account: {fname} {lname}\n• ID: {pid}"

        return "LinkedIn access is unavailable. Reconnect the account and check that profile permissions were approved."
    except Exception as e:
        return "LinkedIn could not be reached. Please try checking its status again later."

@config.require_admin
def post_to_linkedin(text: str) -> str:
    """Prepare a public post preview; publication requires separate Telegram approval."""
    if not config.LINKEDIN_ACCESS_TOKEN:
        return SETUP_MESSAGE
    text = text.strip()
    if not text or len(text) > 3000:
        return "Please provide a LinkedIn post between 1 and 3,000 characters. Nothing was published."
    draft = {"text": text, "expires": time.monotonic() + 1800,
             "account": hashlib.sha256(config.LINKEDIN_ACCESS_TOKEN.encode()).hexdigest()}
    with _draft_lock:
        _drafts[config.get_current_user_id()] = draft
    return preview(draft)

@config.require_admin
def _publish_post(text: str) -> str:
    """
    Publishes an update or post to your LinkedIn profile feed.
    """
    token = config.LINKEDIN_ACCESS_TOKEN
    if not token:
        return SETUP_MESSAGE

    if not text or not text.strip():
        return "Cannot create an empty LinkedIn post. Please provide text for the post."

    author_urn = get_author_urn(token)
    if not author_urn:
        return "Failed to resolve your LinkedIn Person URN. Please ensure your token has 'openid' / 'profile' permissions, or set LINKEDIN_PERSON_URN in .env."

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0"
    }

    # 1. Try UGC Posts API (Universal Share Content)
    payload_ugc = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {
                    "text": text.strip()
                },
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        }
    }

    try:
        response = requests.post(
            "https://api.linkedin.com/v2/ugcPosts",
            json=payload_ugc,
            headers=headers,
            timeout=15
        )

        if response.status_code in (200, 201):
            post_id = response.headers.get("X-RestLi-Id", "")
            return "Post successfully published on LinkedIn." + (f"\nPost ID: {post_id}" if post_id else "")

        if response.status_code in (401, 403):
            return "LinkedIn rejected publication. Reconnect the account and check the Share on LinkedIn permission. Nothing was retried."
        return "LinkedIn did not confirm publication. Check your profile before creating another post; nothing was retried."
    except Exception as e:
        return "LinkedIn delivery is uncertain. Check your profile before trying again to avoid a duplicate post."
