from django.db import connection
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health(_request):
    with connection.cursor() as cur:
        cur.execute("SELECT 1")
        db_ok = cur.fetchone()[0] == 1
    return Response(
        {
            "status": "ok",
            "db": "ok" if db_ok else "error",
            "db_vendor": connection.vendor,
            "now": timezone.now().isoformat(),
        }
    )
