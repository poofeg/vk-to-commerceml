import base64
import hashlib
import secrets

from yarl import URL

OAUTH_URL = URL('https://id.vk.ru/authorize')


def generate_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(32)
    verifier_sha256 = hashlib.sha256(verifier.encode('ascii')).digest()
    challenge = base64.urlsafe_b64encode(verifier_sha256).rstrip(b'=').decode('ascii')
    return verifier, challenge


def get_authorization_url(client_id: str, oauth_callback_url: str, state: str) -> tuple[str, str]:
    verifier, challenge = generate_pkce()
    url = OAUTH_URL.with_query({
        'client_id': client_id,
        'redirect_uri': oauth_callback_url,
        'scope': 'offline,market',
        'response_type': 'code',
        'state': state,
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
    })
    return str(url), verifier
