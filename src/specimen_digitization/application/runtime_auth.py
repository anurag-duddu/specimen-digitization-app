"""Firebase SDK verification; membership authorization remains in the repository."""

import re

from firebase_admin import auth, app_check


class EmailVerificationRequired(PermissionError):
    pass


def _museum_email(value):
    if not isinstance(value, str) or not value.isascii() or len(value) > 254:
        return False
    local, separator, domain = value.partition("@")
    return (
        separator == "@"
        and domain.lower() == "fieldmuseum.org"
        and 0 < len(local) <= 64
        and not local.startswith(".")
        and not local.endswith(".")
        and ".." not in local
        and re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+", local) is not None
    )


def firebase_verifier(firebase_app, allowed_app_ids, app_check_app):
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
        if not _museum_email(claims.get("email")):
            raise PermissionError("Museum email required")
        return uid

    return verify
