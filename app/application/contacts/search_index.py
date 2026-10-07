"""Transactional exact-search index, with ciphertext-validated legacy fallback."""

from itertools import islice
from typing import Any, Literal
from uuid import UUID

from app.application.contacts.identity import ContactIdentityHasher
from app.application.contacts.name_index import ContactNameIndex
from app.application.contacts.search import ContactSearch, identities
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.contact_search import (
    ContactSearchStateModel,
    ContactSearchTokenModel,
)
from app.security.secret_cipher import SecretCipher
from sqlalchemy import Select, and_, delete, insert, select
from sqlalchemy.orm import Session


class ContactSearchIndex:
    def __init__(
        self, session: Session, cipher: SecretCipher, hasher: ContactIdentityHasher
    ) -> None:
        self.session, self.cipher, self.hasher = session, cipher, hasher

    def valid(self, org: UUID) -> Any:
        state = ContactSearchStateModel
        return and_(
            state.organization_id == org,
            state.contact_id == ContactModel.id,
            state.organization_id == ContactModel.organization_id,
            state.key_id == self.hasher.search_key_id,
            state.channel_type == ContactModel.channel_type,
            state.identifier_ciphertext == ContactModel.external_identifier_ciphertext,
            state.registration_ciphertext.is_not_distinct_from(
                ContactModel.registration_ciphertext
            ),
        )

    def matching(self, org: UUID, matcher: ContactSearch) -> Select[tuple[UUID]]:
        if matcher.field == "name":
            raise ValueError("The protected index supports exact identities only")
        state, token = ContactSearchStateModel, ContactSearchTokenModel
        indexed = (
            select(token.contact_id)
            .join(
                state,
                (state.organization_id == token.organization_id)
                & (state.contact_id == token.contact_id),
            )
            .join(ContactModel, self.valid(org))
            .where(
                token.organization_id == org,
                token.field == matcher.field,
                token.digest
                == self.hasher.search_digest(org, matcher.field, matcher.term),
            )
        )
        valid = select(state.contact_id).where(self.valid(org)).exists()
        pending = self.session.scalars(
            select(ContactModel)
            .where(
                ContactModel.organization_id == org,
                ~valid,
            )
            .execution_options(yield_per=256)
        )
        # A key rotation, unexpected SQL update or legacy contact cannot hide a match.
        fallback = [row.id for row in pending if matcher.matches(row)]
        if fallback:
            return select(ContactModel.id).where(
                ContactModel.organization_id == org,
                ContactModel.id.in_(indexed) | ContactModel.id.in_(fallback),
            )
        return indexed

    def _replace(self, org: UUID, contacts: list[ContactModel]) -> None:
        if not contacts:
            return
        ids = [c.id for c in contacts]
        for model in (ContactSearchTokenModel, ContactSearchStateModel):
            self.session.execute(
                delete(model).where(
                    model.organization_id == org, model.contact_id.in_(ids)
                )
            )
        states, tokens = [], []
        for contact in contacts:
            if contact.organization_id != org:
                raise ValueError("Contact search index tenant mismatch")
            states.append(
                {
                    "organization_id": org,
                    "contact_id": contact.id,
                    "key_id": self.hasher.search_key_id,
                    "channel_type": contact.channel_type,
                    "identifier_ciphertext": contact.external_identifier_ciphertext,
                    "registration_ciphertext": contact.registration_ciphertext,
                }
            )
            for kind, value in identities(contact, self.cipher):
                field: Literal["phone", "email"] = (
                    "phone" if kind == "teléfono" else "email"
                )
                tokens.append(
                    {
                        "organization_id": org,
                        "contact_id": contact.id,
                        "field": field,
                        "digest": self.hasher.search_digest(org, field, value),
                    }
                )
        self.session.execute(insert(ContactSearchStateModel), states)
        if tokens:
            self.session.execute(insert(ContactSearchTokenModel), tokens)
        ContactNameIndex(self.session, self.cipher, self.hasher).replace(org, contacts)

    def sync(self, contact: ContactModel) -> None:
        self.session.flush()
        row = self.session.scalar(
            select(ContactModel)
            .where(
                ContactModel.id == contact.id,
                ContactModel.organization_id == contact.organization_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise ValueError("Contact disappeared before indexing")
        self._replace(row.organization_id, [row])

    def rebuild(self, org: UUID) -> int:
        """Caller authorizes maintenance and commits; no contact timestamps change."""
        rows = iter(
            self.session.scalars(
                select(ContactModel)
                .where(
                    ContactModel.organization_id == org,
                )
                .order_by(ContactModel.id)
                .with_for_update()
                .execution_options(yield_per=256)
            )
        )
        count = 0
        while batch := list(islice(rows, 256)):
            self._replace(org, batch)
            count += len(batch)
        return count
