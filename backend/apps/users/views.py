from rest_framework import generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .permissions import IsAdmin
from .serializers import RegistrationSerializer, UserSerializer


class RegisterView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = RegistrationSerializer


@api_view(["GET"])
def me(request):
    """Returns the authenticated user. Confirms JWT auth wiring end-to-end."""
    return Response(UserSerializer(request.user).data)


@api_view(["GET"])
@permission_classes([IsAdmin])
def admin_ping(_request):
    """Permission probe: returns 200 only for users with role=admin, 403 otherwise.
    Exists to make the IsAdmin role class observable from the outside."""
    return Response({"role": "admin"})
