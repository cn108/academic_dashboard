"""A very small Paystack client.

Only two things are needed for school fees: starting a transaction and checking
that a webhook really came from Paystack. Both live here so the views stay
readable and the network call is easy to stub in tests.
"""

import hashlib
import hmac
import json
import urllib.error
import urllib.request

from django.conf import settings

PAYSTACK_INITIALIZE_URL = "https://api.paystack.co/transaction/initialize"
REQUEST_TIMEOUT_SECONDS = 15


class PaystackError(Exception):
    """A readable failure the API can return to the parent."""


def _error_message(error: urllib.error.HTTPError) -> str:
    try:
        payload = json.loads(error.read() or b"{}")
    except (ValueError, OSError):
        payload = {}
    message = payload.get("message") if isinstance(payload, dict) else None
    return message or "Paystack rejected the payment. Try again in a moment."


def initialize_transaction(
    *,
    email: str,
    amount_kobo: int,
    reference: str,
    callback_url: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """Start a Paystack transaction and return its data payload.

    Raises :class:`PaystackError` with a message suitable for a parent when the
    gateway is not configured, unreachable or refuses the transaction.
    """
    secret = settings.PAYSTACK_SECRET_KEY
    if not secret:
        raise PaystackError("Online payments are not set up yet. Please pay at the school office.")

    payload: dict = {"email": email, "amount": amount_kobo, "reference": reference}
    if callback_url:
        payload["callback_url"] = callback_url
    if metadata:
        payload["metadata"] = metadata

    request = urllib.request.Request(
        PAYSTACK_INITIALIZE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        raise PaystackError(_error_message(error)) from error
    except urllib.error.URLError as error:
        raise PaystackError(
            "Could not reach Paystack. Check the internet connection and try again."
        ) from error
    except ValueError as error:
        raise PaystackError("Paystack returned an unexpected response.") from error

    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict) or not data.get("authorization_url"):
        message = body.get("message") if isinstance(body, dict) else None
        raise PaystackError(message or "Paystack did not return a checkout link.")
    return data


def signature_for(body: bytes) -> str:
    """The HMAC SHA512 Paystack signs a webhook body with."""
    return hmac.new(settings.PAYSTACK_SECRET_KEY.encode("utf-8"), body, hashlib.sha512).hexdigest()


def verify_signature(body: bytes, provided: str | None) -> bool:
    """True only for a signature Paystack could have produced."""
    if not settings.PAYSTACK_SECRET_KEY or not provided:
        return False
    return hmac.compare_digest(signature_for(body), provided)
