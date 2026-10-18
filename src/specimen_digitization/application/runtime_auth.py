"""Firebase SDK verification; membership authorization remains in the repository."""

import re

from firebase_admin import auth, app_check


class EmailVerificationRequired(PermissionError):
    pass


def _normalized_email(value):
    if not isinstance(value, str) or not value.isascii() or len(value) > 254:
        return None
    local, separator, domain = value.partition("@")
    valid = (
        separator == "@"
        and 0 < len(local) <= 64
        and not local.startswith(".")
        and not local.endswith(".")
        and ".." not in local
        and re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+", local) is not None
        and len(domain.split('.')) >= 2
        and all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label)
                for label in domain.split('.'))
    )
    return value.lower() if valid else None


def validated_external_emails(values):
    """Exact server-owned exceptions; no domain, wildcard, dot or plus folding."""
    if not isinstance(values, (list, tuple, set, frozenset)) or len(values) > 100:
        raise ValueError('External email admission requires a list of exact addresses')
    normalized = [_normalized_email(value) for value in values]
    if any(value is None or '*' in value or '?' in value for value in normalized):
        raise ValueError('External email admission requires exact ASCII addresses')
    return frozenset(normalized)


def _museum_email(value):
    normalized = _normalized_email(value)
    return normalized is not None and (
        normalized.endswith('@fieldmuseum.org')
        or normalized == 'anurag@infinative.com'
    )


def firebase_verifier(firebase_app, allowed_app_ids, app_check_app, *, external_email_allowlist=()):
    admitted_external = validated_external_emails(external_email_allowlist)
    def verify(token, check_token):
        if (
            not token
            or not check_token
            or len(token) > 16384
            or len(check_token) > 16384
        ):
            raise PermissionError("Firebase identity or App Check rejected")
        try:
            checked = app_check.verify_token(check_token, app=app_check_app)
            expected_issuer = (
                "https://firebaseappcheck.googleapis.com/" + app_check_app.project_id
            )
            if checked.get("iss") != expected_issuer:
                raise ValueError("Wrong App Check issuer")
            if checked.get("app_id") not in allowed_app_ids:
                raise ValueError("Unapproved application")
            claims = auth.verify_id_token(token, app=firebase_app, check_revoked=True)
            uid = claims.get("uid")
            if not isinstance(uid, str) or not uid or len(uid) > 128:
                raise ValueError("Invalid identity")
        except Exception as exc:
            raise PermissionError("Firebase identity or App Check rejected") from exc
        if claims.get("email_verified") is not True:
            raise EmailVerificationRequired("Verified email required")
        email = claims.get('email')
        if not _museum_email(email) and _normalized_email(email) not in admitted_external:
            raise PermissionError("Museum email required")
        return uid

    return verify
