from django.urls import path

from .views import SyncPullView

app_name = "sync"

urlpatterns = [
    path("pull/", SyncPullView.as_view(), name="pull"),
]
