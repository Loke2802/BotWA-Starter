"""Compact protected signals; decrypt only stale data and the requested page."""

from collections import defaultdict
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session, load_only

from app.application.contacts.identity import ContactIdentityHasher
from app.application.contacts.name_index import ContactNameIndex
from app.application.contacts.search import identities, normalized_name
from app.application.contacts.search_index import ContactSearchIndex
from app.domain.contacts.contracts import ContactIdentityNormalizer
from app.domain.crm.growth_contracts import DuplicateCandidate, DuplicateList
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.contact_name_search import (
    ContactNameStateModel,
    ContactNameTokenModel,
)
from app.infrastructure.models.contact_search import (
    ContactSearchStateModel,
    ContactSearchTokenModel,
)
from app.infrastructure.models.crm_contact_merge import ContactMergeModel
from app.security.secret_cipher import SecretCipher


class DuplicateIndex:
    def __init__(self, session: Session, cipher: SecretCipher, digest_key: str) -> None:
        self.session, self.cipher = session, cipher
        self.hasher = ContactIdentityHasher(digest_key, ContactIdentityNormalizer())

    def candidates(self, org: UUID, page: int) -> DuplicateList:
        contact = ContactModel
        active = (
            (contact.organization_id == org)
            & (contact.status == "active")
            & contact.id.not_in(
                select(ContactMergeModel.source_id).where(
                    ContactMergeModel.organization_id == org
                )
            )
        )
        exact = ContactSearchIndex(self.session, self.cipher, self.hasher)
        names = ContactNameIndex(self.session, self.cipher, self.hasher)
        signals: dict[UUID, set[tuple[str, str]]] = defaultdict(set)
        state, token = ContactSearchStateModel, ContactSearchTokenModel
        ns, nt = ContactNameStateModel, ContactNameTokenModel
        fallback_identity: set[tuple[str, str]] = set()
        fallback_names: set[str] = set()
        valid_identity = select(state.contact_id).where(exact.valid(org)).exists()
        for row in self.session.scalars(
            select(contact)
            .where(active, ~valid_identity)
            .execution_options(yield_per=256)
        ):
            for kind, value in identities(row, self.cipher):
                fallback_field: Literal["phone", "email"] = (
                    "phone" if kind == "teléfono" else "email"
                )
                digest = self.hasher.search_digest(org, fallback_field, value)
                signals[row.id].add((kind, digest))
                fallback_identity.add((fallback_field, digest))
        valid_name = select(ns.contact_id).where(names.valid(org)).exists()
        for row in self.session.scalars(
            select(contact)
            .options(load_only(contact.id, contact.display_name_ciphertext))
            .where(active, ~valid_name)
            .execution_options(yield_per=256)
        ):
            value = (
                normalized_name(self.cipher.decrypt(row.display_name_ciphertext))
                if row.display_name_ciphertext
                else ""
            )
            if len(value) >= 3:
                digest = self.hasher.name_digest(org, "exact", value)
                signals[row.id].add(("nombre", digest))
                fallback_names.add(digest)
        valid_signals = (
            select(token.contact_id, token.field, token.digest)
            .join(
                state,
                (state.organization_id == token.organization_id)
                & (state.contact_id == token.contact_id),
            )
            .join(contact, exact.valid(org))
            .where(active, token.organization_id == org)
        ).subquery()
        shared = (
            select(valid_signals.c.field, valid_signals.c.digest)
            .group_by(valid_signals.c.field, valid_signals.c.digest)
            .having(func.count() > 1)
            .correlate(None)
        )
        key = tuple_(valid_signals.c.field, valid_signals.c.digest)
        for ident, field, digest in self.session.execute(
            select(valid_signals)
            .where(key.in_(shared) | key.in_(fallback_identity))
            .execution_options(yield_per=256)
        ):
            signals[ident].add(("teléfono" if field == "phone" else "correo", digest))
        valid_names = (
            select(nt.contact_id, nt.digest)
            .join(
                ns,
                (ns.organization_id == nt.organization_id)
                & (ns.contact_id == nt.contact_id),
            )
            .join(contact, names.valid(org))
            .where(active, nt.organization_id == org, nt.kind == "exact")
        ).subquery()
        shared_names = (
            select(valid_names.c.digest)
            .group_by(valid_names.c.digest)
            .having(func.count() > 1)
            .correlate(None)
        )
        for ident, digest in self.session.execute(
            select(valid_names)
            .where(
                valid_names.c.digest.in_(shared_names)
                | valid_names.c.digest.in_(fallback_names)
            )
            .execution_options(yield_per=256)
        ):
            signals[ident].add(("nombre", digest))
        anchors: dict[tuple[str, str], UUID] = {}
        pairs: list[tuple[UUID, UUID, list[str]]] = []
        scanned = (
            self.session.scalar(select(func.count()).select_from(contact).where(active))
            or 0
        )
        total = 0
        start = (page - 1) * 20
        for ident in self.session.scalars(
            select(contact.id)
            .where(active, contact.id.in_(list(signals)))
            .order_by(contact.created_at, contact.id)
            .execution_options(yield_per=256)
        ):
            matches: dict[UUID, list[str]] = defaultdict(list)
            for signal in signals.pop(ident, set()):
                anchor = anchors.setdefault(signal, ident)
                if anchor != ident:
                    matches[anchor].append(signal[0])
            for target in sorted(matches, key=str):
                if start <= total < start + 20:
                    pairs.append((ident, target, sorted(set(matches[target]))))
                total += 1
        ids = {ident for source, target, _ in pairs for ident in (source, target)}
        display = {
            row.id: (
                self.cipher.decrypt(row.display_name_ciphertext)
                if row.display_name_ciphertext
                else "Sin nombre"
            )
            for row in self.session.scalars(
                select(contact)
                .options(load_only(contact.id, contact.display_name_ciphertext))
                .where(contact.organization_id == org, contact.id.in_(ids))
            )
        }
        return DuplicateList(
            items=[
                DuplicateCandidate(
                    source_id=a,
                    target_id=b,
                    source_name=display[a],
                    target_name=display[b],
                    reasons=reasons,
                )
                for a, b, reasons in pairs
            ],
            page=page,
            has_next=page * 20 < total,
            scanned=scanned,
            scan_limited=False,
            total=total,
        )
