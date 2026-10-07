"""Name-only index; candidate verification preserves arbitrary partial words."""

from typing import Any
from uuid import UUID

from app.application.contacts.identity import ContactIdentityHasher
from app.application.contacts.search import ContactSearch, normalized_name
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.contact_name_search import (
    ContactNameStateModel,
    ContactNameTokenModel,
)
from app.infrastructure.repositories.contact_search_ids import matching_contact_ids
from app.security.secret_cipher import SecretCipher
from sqlalchemy import Select, and_, delete, func, insert, select
from sqlalchemy.orm import Session, load_only


def name_grams(name: str) -> set[str]:
    return {
        word[i : i + size]
        for word in name.split()
        for size in (1, 2)
        for i in range(len(word) - size + 1)
    }


def query_grams(term: str) -> set[str]:
    # Single-letter words remain valid when the complete query has >=2 characters.
    return {
        word[i : i + min(2, len(word))]
        for word in term.split()
        for i in range(max(1, len(word) - 1))
    }


class ContactNameIndex:
    def __init__(
        self, session: Session, cipher: SecretCipher, hasher: ContactIdentityHasher
    ) -> None:
        self.session, self.cipher, self.hasher = session, cipher, hasher

    def valid(self, org: UUID) -> Any:
        state = ContactNameStateModel
        return and_(
            state.organization_id == org,
            state.organization_id == ContactModel.organization_id,
            state.contact_id == ContactModel.id,
            state.key_id == self.hasher.search_key_id,
            state.name_ciphertext.is_not_distinct_from(
                ContactModel.display_name_ciphertext
            ),
        )

    def matching(self, org: UUID, matcher: ContactSearch) -> Select[tuple[UUID]]:
        if matcher.field != "name":
            raise ValueError("A name query is required")
        state, token = ContactNameStateModel, ContactNameTokenModel
        digests = {
            self.hasher.name_digest(org, "gram", value)
            for value in query_grams(matcher.term)
        }
        gram_matches = (
            select(token.contact_id)
            .where(
                token.organization_id == org,
                token.kind == "gram",
                token.digest.in_(digests),
            )
            .group_by(token.contact_id)
            # The token primary key makes each (contact, kind, digest) unique.
            .having(func.count() == len(digests))
        ).subquery()
        # Reduce gram matches before validating snapshots. Otherwise PostgreSQL
        # can choose a token-index lookup for every contact in a broad search.
        indexed = (
            select(gram_matches.c.contact_id)
            .join(
                state,
                (state.contact_id == gram_matches.c.contact_id)
                & (state.organization_id == org),
            )
            .join(ContactModel, self.valid(org))
        )
        valid = select(state.contact_id).where(self.valid(org)).exists()
        if all(len(word) <= 2 for word in matcher.term.split()):
            # A stored one/two-character gram is already the exact substring.
            # Broad short queries need not decrypt every matching name to count it.
            pending = self.session.scalars(
                select(ContactModel)
                .options(
                    load_only(ContactModel.id, ContactModel.display_name_ciphertext)
                )
                .where(ContactModel.organization_id == org, ~valid)
                .execution_options(yield_per=256)
            )
            fallback = [row.id for row in pending if matcher.matches(row)]
            if not fallback:
                return indexed
            return select(ContactModel.id).where(
                ContactModel.organization_id == org,
                ContactModel.id.in_(indexed)
                | ContactModel.id.in_(
                    matching_contact_ids(self.session, org, fallback)
                ),
            )
        candidate_ids = indexed.union_all(
            select(ContactModel.id).where(ContactModel.organization_id == org, ~valid)
        )
        candidates = self.session.scalars(
            select(ContactModel)
            .options(load_only(ContactModel.id, ContactModel.display_name_ciphertext))
            .where(
                ContactModel.organization_id == org,
                # Disjoint branches avoid a correlated validity lookup per row
                # in the OR plan; current snapshots still gate indexed results.
                ContactModel.id.in_(candidate_ids),
            )
            .execution_options(yield_per=256)
        )
        # Grams may occur in different words/order: always verify exact semantics.
        matches = [row.id for row in candidates if matcher.matches(row)]
        return matching_contact_ids(self.session, org, matches)

    def replace(self, org: UUID, contacts: list[ContactModel]) -> None:
        if not contacts:
            return
        ids = [row.id for row in contacts]
        for model in (ContactNameTokenModel, ContactNameStateModel):
            self.session.execute(
                delete(model).where(
                    model.organization_id == org, model.contact_id.in_(ids)
                )
            )
        states, tokens = [], []
        for row in contacts:
            if row.organization_id != org:
                raise ValueError("Contact name index tenant mismatch")
            states.append(
                dict(
                    organization_id=org,
                    contact_id=row.id,
                    key_id=self.hasher.search_key_id,
                    name_ciphertext=row.display_name_ciphertext,
                )
            )
            name = (
                normalized_name(self.cipher.decrypt(row.display_name_ciphertext))
                if row.display_name_ciphertext
                else ""
            )
            for gram in name_grams(name):
                tokens.append(
                    dict(
                        organization_id=org,
                        contact_id=row.id,
                        kind="gram",
                        digest=self.hasher.name_digest(org, "gram", gram),
                    )
                )
            if len(name) >= 3:
                tokens.append(
                    dict(
                        organization_id=org,
                        contact_id=row.id,
                        kind="exact",
                        digest=self.hasher.name_digest(org, "exact", name),
                    )
                )
        self.session.execute(insert(ContactNameStateModel), states)
        if tokens:
            # Send bounded multi-row statements rather than one round trip/token.
            # 200*4 parameters also stays below SQLite's conservative 999 limit.
            for offset in range(0, len(tokens), 200):
                self.session.execute(
                    insert(ContactNameTokenModel).values(tokens[offset : offset + 200])
                )

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
            raise ValueError("Contact disappeared before name indexing")
        self.replace(row.organization_id, [row])
