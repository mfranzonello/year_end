"""Authenticate Streamlit users and enforce the initial owner-only admin role."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import streamlit as st


@dataclass(frozen=True)
class AppIdentity:
    """Normalized identity and authorization state for one Streamlit session."""

    is_authenticated: bool
    subject: str | None
    display_name: str | None
    is_admin: bool


def resolve_identity(
    user: Mapping[str, object],
    admin_subjects: Iterable[str],
) -> AppIdentity:
    """Resolve authentication and owner authorization from OIDC claims."""
    is_authenticated = bool(user.get("is_logged_in", False))
    subject_value = user.get("sub") if is_authenticated else None
    subject = str(subject_value).strip() if subject_value else None
    allowed_subjects = {value.strip() for value in admin_subjects if value.strip()}
    display_value = (
        user.get("name") or user.get("email")
        if is_authenticated
        else None
    )
    display_name = str(display_value).strip() if display_value else None
    return AppIdentity(
        is_authenticated=is_authenticated,
        subject=subject,
        display_name=display_name,
        is_admin=subject is not None and subject in allowed_subjects,
    )


def authentication_configured() -> bool:
    """Return whether the default OIDC provider has its required configuration."""
    auth = st.secrets.get("auth", {})
    required = (
        "redirect_uri",
        "cookie_secret",
        "client_id",
        "client_secret",
        "server_metadata_url",
    )
    return isinstance(auth, Mapping) and all(
        isinstance(auth.get(key), str) and auth[key].strip()
        for key in required
    )


def current_identity() -> AppIdentity:
    """Return the normalized identity for the active Streamlit session."""
    authorization = st.secrets.get("authorization", {})
    admin_subjects = (
        authorization.get("admin_subjects", [])
        if isinstance(authorization, Mapping)
        else []
    )
    return resolve_identity(st.user, admin_subjects)


def render_account_controls(identity: AppIdentity) -> None:
    """Render login state and account actions in the current container."""
    if identity.is_authenticated:
        st.caption(identity.display_name or "Signed in")
        st.badge("Administrator" if identity.is_admin else "Reader")
        if not identity.is_admin and identity.subject:
            st.caption(f"Authorization subject: `{identity.subject}`")
        if st.button("Sign out", key="account_sign_out"):
            st.logout()
        return

    if authentication_configured():
        if st.button("Administrator sign in", type="primary", key="account_sign_in"):
            st.login()
    else:
        st.caption("Administrator sign-in is not configured for this deployment.")


def require_admin() -> AppIdentity:
    """Stop the active page unless its signed-in user is an administrator."""
    identity = current_identity()
    if not identity.is_authenticated:
        st.error("Administrator sign-in is required to view this page.")
        if authentication_configured() and st.button("Sign in", type="primary"):
            st.login()
        st.stop()
    if not identity.is_admin:
        st.error("Your account does not have administrator access.")
        st.stop()
    return identity
