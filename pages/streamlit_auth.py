"""Authenticate Google users and enforce database-backed application tiers."""

from collections.abc import Iterable, Mapping

from sqlalchemy.exc import SQLAlchemyError
from database.db import get_engine
from database import db_admin
from dataclasses import dataclass

import streamlit as st


TIERS = ("demo", "viewer", "member", "admin")


@dataclass(frozen=True)
class AppIdentity:
    """Normalized identity and authorization state for one Streamlit session."""

    is_authenticated: bool
    subject: str | None
    display_name: str | None
    roles: frozenset[str]

    @property
    def is_admin(self) -> bool:
        """Return whether the database assigned administrator access."""
        return "admin" in self.roles

    @property
    def tier(self) -> str:
        """Return the highest recognized tier; unassigned accounts fail closed."""
        return next((role for role in reversed(TIERS) if role in self.roles), "anonymous")


def resolve_identity(
    user: Mapping[str, object],
    roles: Iterable[str],
) -> AppIdentity:
    """Combine authenticated claims with roles fetched from the database."""
    is_authenticated = bool(user.get("is_logged_in", False))
    subject_value = user.get("sub") if is_authenticated else None
    subject = str(subject_value).strip() if subject_value else None
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
        roles=frozenset(roles) if subject else frozenset(),
    )


def authentication_configured() -> bool:
    """Return whether Google OIDC and the shared cookie settings are configured."""
    auth = st.secrets.get("auth", {})
    if not isinstance(auth, Mapping):
        return False
    google = auth.get("google", {})
    return isinstance(google, Mapping) and all(
        isinstance(section.get(key), str) and bool(section[key].strip())
        for section, keys in (
            (auth, ("redirect_uri", "cookie_secret")),
            (google, ("client_id", "client_secret", "server_metadata_url")),
        )
        for key in keys
    )


@st.cache_resource
def identity_engine():
    """Reuse the deployment database pool without caching authorization results."""
    settings = st.secrets["postgresql"]
    return get_engine(settings["host"], settings.get("port", "5432"),
                      settings["database"], settings["user"], settings["password"])


def current_identity() -> AppIdentity:
    """Register new identities and read current database roles on every check."""
    user = st.user
    if not user.get("is_logged_in", False):
        st.session_state.pop("identity_login_observed", None)
        return resolve_identity(user, ())
    subject = user.get("sub")
    if not subject or user.get("iss") not in ("https://accounts.google.com", "accounts.google.com"):
        st.error("The signed-in account has an unsupported or incomplete identity.")
        st.stop()
    issuer = "Google"
    key = (issuer, str(subject))
    try:
        engine = identity_engine()
        record = db_admin.fetch_identity(engine, *key)
        if record.empty:
            db_admin.create_identity(engine, *key, user.get("email"), user.get("name"))
        if st.session_state.get("identity_login_observed") != key:
            db_admin.update_identity_login(engine, *key)
            st.session_state["identity_login_observed"] = key
        roles = db_admin.fetch_identity_role(engine, *key)["role_name"].tolist()
    except (SQLAlchemyError, ValueError):
        st.error("Account access could not be loaded. Contact the administrator or retry later.")
        st.stop()
    return resolve_identity(user, roles)


def current_tier() -> str:
    """Return the highest assigned tier for navigation and data selection."""
    return current_identity().tier


def require_any_tier(*allowed: str) -> AppIdentity:
    """Stop execution unless the current tier is explicitly allowed."""
    if not allowed or any(role not in (*TIERS, "anonymous") for role in allowed):
        raise ValueError("Specify recognized access tiers.")
    identity = current_identity()
    if identity.tier not in allowed:
        st.error("Your account does not have access to this page or action.")
        st.stop()
    return identity


def require_tier(minimum: str) -> AppIdentity:
    """Require a recognized minimum tier, including higher tiers."""
    if minimum not in TIERS:
        raise ValueError("Specify a recognized signed-in tier.")
    return require_any_tier(*TIERS[TIERS.index(minimum):])


def render_account_controls(identity: AppIdentity) -> None:
    """Render login state and account actions in the current container."""
    if identity.is_authenticated:
        st.caption(identity.display_name or "Signed in")
        st.badge("Administrator" if identity.is_admin else (identity.tier.title() if identity.roles else "No access"))
        if st.button("Sign out", key="account_sign_out"):
            st.logout()
        return

    if authentication_configured():
        if st.button("Sign in with Google", type="primary", key="account_sign_in"):
            st.login("google")
    else:
        st.caption("Sign-in is not configured for this deployment.")


def require_admin() -> AppIdentity:
    """Retain the administrator guard for existing callers."""
    return require_tier("admin")
