import os
import logging
import requests
import config

logger = logging.getLogger("YoBotLinkedIn")

_CACHED_PERSON_URN = None

@config.require_admin
def get_author_urn(token: str) -> str:
    global _CACHED_PERSON_URN
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
        return "LinkedIn is not linked yet. Please add LINKEDIN_ACCESS_TOKEN to your .env file."

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

        return f"⚠️ LinkedIn Authentication Error: {res.status_code} - {res.text}"
    except Exception as e:
        return f"Failed to connect to LinkedIn: {e}"

@config.require_admin
def post_to_linkedin(text: str) -> str:
    """
    Publishes an update or post to your LinkedIn profile feed.
    """
    token = config.LINKEDIN_ACCESS_TOKEN
    if not token:
        return "LinkedIn is not linked yet. Please add LINKEDIN_ACCESS_TOKEN to your .env file."

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
            data = response.json()
            post_id = data.get("id", "Success")
            return f"🚀 Post successfully published on LinkedIn!\nPost ID: {post_id}"

        # 2. If ugcPosts fails with 400 or 403, try modern Posts API
        rest_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "LinkedIn-Version": "202401",
            "X-Restli-Protocol-Version": "2.0.0"
        }
        rest_payload = {
            "author": author_urn,
            "commentary": text.strip(),
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": []
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False
        }
        res_rest = requests.post("https://api.linkedin.com/rest/posts", json=rest_payload, headers=rest_headers, timeout=15)
        if res_rest.status_code in (200, 201):
            return "🚀 Post successfully published on LinkedIn!"

        return f"LinkedIn post failed (Status {response.status_code}): {response.text}"
    except Exception as e:
        return f"Error publishing to LinkedIn: {e}"
