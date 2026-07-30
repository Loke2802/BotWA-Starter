import hashlib
import hmac


class WhatsAppWebhookSignatureVerifier:
    _PREFIX = "sha256="

    def verify(
        self,
        raw_body: bytes,
        signature_header: str | None,
        app_secret: str,
    ) -> bool:
        if not signature_header or not signature_header.startswith(self._PREFIX):
            return False
        supplied_digest = signature_header[len(self._PREFIX) :]
        if len(supplied_digest) != 64:
            return False
        expected_digest = hmac.new(
            app_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected_digest, supplied_digest)
