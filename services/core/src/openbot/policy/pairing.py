"""Local-initiated short-TTL pairing challenge, pending candidate store, and owner revocation."""

import hashlib
import hmac
import secrets
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Literal

from openbot.contracts import canonicalize, strict_json
from openbot.storage.inbox import InboundContext, authorize
from openbot.storage.writer import LookupResult, Writer, WriterCommand


@dataclass(frozen=True, slots=True)
class PairingChallenge:
    challenge_id: str
    profile_id: str
    expected_tenant_key: str
    expected_app_id: str
    code: str
    expires_monotonic_ms: int
    max_attempts: int


@dataclass(frozen=True, slots=True)
class PendingPairingCandidate:
    candidate_id: str
    challenge_id: str
    tenant_key: str
    app_id: str
    open_id: str
    display_name: str
    status: Literal["PENDING_LOCAL_CONFIRMATION"]


class PairingService:
    """Control-owned pairing: remote claims only create pending candidates; local confirms."""

    def __init__(self, writer: Writer) -> None:
        self._writer = writer
        self._challenges: dict[str, PairingChallenge] = {}
        self._attempts_used: dict[str, int] = {}
        self._claimed_challenges: set[str] = set()
        self._candidates: dict[str, PendingPairingCandidate] = {}

    def create_local_challenge(
        self,
        *,
        profile_id: str,
        expected_tenant_key: str,
        expected_app_id: str,
        ttl_ms: int = 60_000,
        max_attempts: int = 3,
    ) -> PairingChallenge:
        if ttl_ms <= 0 or max_attempts <= 0:
            raise ValueError("ttl_ms and max_attempts must be positive")
        now_mono = int(time.monotonic() * 1000)
        chal = PairingChallenge(
            challenge_id="pch_" + secrets.token_hex(12),
            profile_id=profile_id,
            expected_tenant_key=expected_tenant_key,
            expected_app_id=expected_app_id,
            code=secrets.token_hex(6).upper(),
            expires_monotonic_ms=now_mono + ttl_ms,
            max_attempts=max_attempts,
        )
        self._challenges[chal.challenge_id] = chal
        self._attempts_used[chal.challenge_id] = 0
        return chal

    def submit_remote_claim(
        self,
        *,
        challenge_id: str,
        code: str,
        tenant_key: str,
        app_id: str,
        open_id: str,
        display_name: str,
    ) -> PendingPairingCandidate:
        chal = self._challenges.get(challenge_id)
        now_mono = int(time.monotonic() * 1000)
        if (
            chal is None
            or challenge_id in self._claimed_challenges
            or now_mono >= chal.expires_monotonic_ms
        ):
            raise PermissionError("CHALLENGE_ALREADY_CLAIMED_OR_EXPIRED")

        used = self._attempts_used.get(challenge_id, 0) + 1
        self._attempts_used[challenge_id] = used
        if used > chal.max_attempts:
            self._claimed_challenges.add(challenge_id)
            raise PermissionError("CHALLENGE_ATTEMPTS_EXHAUSTED")

        if tenant_key != chal.expected_tenant_key or app_id != chal.expected_app_id:
            raise PermissionError("TENANT_OR_APP_MISMATCH")
        if not hmac.compare_digest(code.strip().upper(), chal.code):
            raise PermissionError("INVALID_PAIRING_CODE")

        self._claimed_challenges.add(challenge_id)
        cand = PendingPairingCandidate(
            candidate_id="pcn_" + secrets.token_hex(12),
            challenge_id=challenge_id,
            tenant_key=tenant_key,
            app_id=app_id,
            open_id=open_id,
            display_name=display_name,
            status="PENDING_LOCAL_CONFIRMATION",
        )
        self._candidates[cand.candidate_id] = cand
        return cand

    def confirm_candidate_locally(
        self,
        context: InboundContext,
        candidate_id: str,
        *,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> dict[str, Any]:
        cand = self._candidates.get(candidate_id)
        if cand is None:
            raise PermissionError("Pending pairing candidate not found")
        fp = hashlib.sha256(
            canonicalize({"kind": "pair_confirm", "cand": candidate_id, "req": request_id})
        ).hexdigest()

        def lookup(db: sqlite3.Connection) -> LookupResult | None:
            return None

        def apply(db: sqlite3.Connection) -> bytes:
            authorize(db, context)
            now = time.time_ns() // 1_000_000
            acct_row = db.execute(
                "SELECT account_id FROM channel_accounts "
                "WHERE channel='feishu' AND tenant_id=? AND app_id=?",
                (cand.tenant_key, cand.app_id),
            ).fetchone()
            if acct_row:
                acct_id = str(acct_row[0])
            else:
                acct_id = "cac_" + secrets.token_hex(10)
                db.execute(
                    "INSERT INTO channel_accounts("
                    "account_id,channel,tenant_id,app_id,secret_ref,status,created_at) "
                    "VALUES(?, 'feishu', ?, ?, 'keychain:feishu:app_secret', 'ACTIVE', ?)",
                    (acct_id, cand.tenant_key, cand.app_id, now),
                )

            ident_id = "cid_" + secrets.token_hex(10)
            db.execute(
                "INSERT INTO channel_identities("
                "identity_id,account_id,external_user_id,principal_id,status,linked_at) "
                "VALUES(?, ?, ?, ?, 'ACTIVE', ?)",
                (ident_id, acct_id, cand.open_id, context.principal_id, now),
            )
            receipt = {
                "candidate_id": candidate_id,
                "principal_id": context.principal_id,
                "identity_id": ident_id,
                "open_id": cand.open_id,
                "status": "ACTIVE_OWNER",
            }
            return canonicalize(receipt)

        raw = self._writer.submit(
            WriterCommand(request_id, fp, "normal", deadline_monotonic_ms, apply, lookup)
        ).result(timeout=5)
        self._candidates.pop(candidate_id, None)
        return dict(strict_json(raw))

    def is_active_owner(self, external_user_id: str) -> bool:
        def query(db: sqlite3.Connection) -> bool:
            row = db.execute(
                "SELECT 1 FROM channel_identities ci "
                "JOIN principals p ON p.principal_id = ci.principal_id "
                "WHERE ci.external_user_id=? AND ci.status='ACTIVE' "
                "AND p.role='OWNER' AND p.status='ACTIVE'",
                (external_user_id,),
            ).fetchone()
            return row is not None

        return bool(self._writer.read(query))

    def revoke_owner(
        self,
        context: InboundContext,
        *,
        principal_id: str,
        request_id: str,
        deadline_monotonic_ms: int,
    ) -> dict[str, Any]:
        fp = hashlib.sha256(
            canonicalize({"kind": "pair_revoke", "principal": principal_id, "req": request_id})
        ).hexdigest()

        def lookup(db: sqlite3.Connection) -> LookupResult | None:
            return None

        def apply(db: sqlite3.Connection) -> bytes:
            authorize(db, context)
            now = time.time_ns() // 1_000_000
            db.execute(
                "UPDATE channel_identities SET status='REVOKED' WHERE principal_id=?",
                (principal_id,),
            )
            db.execute(
                "UPDATE profile_config SET identity_epoch=identity_epoch+1,"
                "version=version+1,updated_at=? WHERE singleton=1",
                (now,),
            )
            new_epoch = int(
                db.execute(
                    "SELECT identity_epoch FROM profile_config WHERE singleton=1"
                ).fetchone()[0]
            )
            return canonicalize(
                {
                    "principal_id": principal_id,
                    "status": "REVOKED",
                    "new_identity_epoch": new_epoch,
                }
            )

        raw = self._writer.submit(
            WriterCommand(request_id, fp, "normal", deadline_monotonic_ms, apply, lookup)
        ).result(timeout=5)
        return dict(strict_json(raw))
