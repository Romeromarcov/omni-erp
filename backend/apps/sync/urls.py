from django.urls import path

from .views import SyncPullView, SyncPushVentasView, SyncPushView

app_name = "sync"

urlpatterns = [
    path("pull/", SyncPullView.as_view(), name="pull"),
    path("push/", SyncPushView.as_view(), name="push"),
    path("push/ventas/", SyncPushVentasView.as_view(), name="push-ventas"),
]
