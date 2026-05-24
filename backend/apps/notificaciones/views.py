from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.core.models import Notificacion

from .serializers import NotificacionSerializer


class NotificacionViewSet(GenericViewSet):
    """
    GET  /api/notificaciones/notificaciones/mis-notificaciones/            → últimas 20
    GET  /api/notificaciones/notificaciones/mis-notificaciones/?no_leidas=true
    PATCH /api/notificaciones/notificaciones/{id}/marcar-leida/
    """

    permission_classes = [IsAuthenticated]
    serializer_class = NotificacionSerializer

    def get_queryset(self):
        return Notificacion.objects.filter(id_usuario=self.request.user)

    @action(detail=False, methods=["get"], url_path="mis-notificaciones")
    def mis_notificaciones(self, request):
        qs = self.get_queryset()

        no_leidas = request.query_params.get("no_leidas", "").lower() in ("true", "1", "yes")
        if no_leidas:
            qs = qs.filter(leida=False)

        qs = qs.order_by("-fecha_creacion")[:20]
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["patch"], url_path="marcar-leida")
    def marcar_leida(self, request, pk=None):
        try:
            notificacion = self.get_queryset().get(pk=pk)
        except Notificacion.DoesNotExist:
            return Response({"detail": "No encontrada."}, status=status.HTTP_404_NOT_FOUND)

        notificacion.marcar_leida()
        serializer = self.get_serializer(notificacion)
        return Response(serializer.data)
