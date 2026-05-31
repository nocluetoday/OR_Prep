import pytest

from apps.cases.models import CaseTemplate
from apps.cases.services.briefing import _load_published_claims
from apps.wiki.models import Claim, ClaimAuditStatus, WikiPage


@pytest.mark.django_db
def test_load_published_claims_excludes_audited_ok_claims():
    case_template = CaseTemplate.objects.create(
        case_type="holep",
        title="HoLEP",
    )
    wiki_page = WikiPage.objects.create(
        case_template=case_template,
        path="operative-technique",
        title="Operative technique",
    )
    Claim.objects.create(
        wiki_page=wiki_page,
        claim_id="audited-ok-only",
        statement="Audited claims are not yet faculty-published.",
        audit_status=ClaimAuditStatus.AUDITED_OK,
    )
    Claim.objects.create(
        wiki_page=wiki_page,
        claim_id="published-claim",
        statement="Published claims may be cited.",
        audit_status=ClaimAuditStatus.PUBLISHED,
    )

    claims = _load_published_claims(case_template)

    assert set(claims) == {"published-claim"}
