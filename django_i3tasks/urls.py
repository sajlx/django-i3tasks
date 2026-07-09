# django-i3tasks — Django app for managing async tasks via HTTP
# Copyright (C) 2024-2026 Ivan Bettarini
# Licensed under the GNU General Public License v3.0 or later.
# See LICENSE in the project root for full text.

# import media_kit.urls as media_kit_urls
# from action.urls import urlpatterns as action_url_patterns

from django.contrib import admin
from django.urls import path

from .views import BeatTaskView, HealthTaskView, PushedTaskView, TaskStatusView


admin.autodiscover()


urlpatterns = [
    path("tasks-push/", PushedTaskView.as_view(), name="i3tasks-push"),
    path("tasks-beat/", BeatTaskView.as_view(), name="i3tasks-beat"),
    path("tasks-health/", HealthTaskView.as_view(), name="i3tasks-health"),
    path("tasks-status/<int:task_id>/", TaskStatusView.as_view(), name="i3tasks-status"),
    path("tasks-status/<uuid:task_uuid>/", TaskStatusView.as_view(), name="i3tasks-status-uuid"),
]
# urlpatterns = [
#     path(r"", core_views.homeview, name="homeview"),
#     path("robots.txt", core_views.robots_txt),
#     path(r"_probe", core_views.probeview, name="probe"),
#     path(r"healtz", core_views.probeview, name="probe"),
#     path(r"healtz_db", core_views.health_check_db, name="probe"),
#     path(r"_status_probe", core_views.probeview, name="status probe"),
#     path(r'admin/', admin.site.urls),
#     path(r'admin/', include('loginas.urls')),
#     re_path(r'user-avatar/(?P<pk>\d+)/', views.UserAvatarView.as_view(), name='user avatar'),
#     path(r'user-choice/', core_views.UserChoiceView.as_view(), name='user choice'),
#     path(r'media-kit/', include(media_kit_urls)),
#     path(r'action/', include(action_url_patterns)),
#     re_path(r'task_status/(?P<task_id>.+)/', core_views.TaskStatusView.as_view(), name='task status'),
#     path(r'', include(router.urls)),
# ] + \
#     api_urls.urlpatterns
