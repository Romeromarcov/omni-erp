from django.urls import path

from .views import SyncPullView, SyncPushVentasView

app_name = "sync"

urlpatterns = [
    path("pull/", SyncPullView.as_view(), name="pull"),
    path("push/ventas/", SyncPushVentasView.as_view(), name="push-ventas"),
]
