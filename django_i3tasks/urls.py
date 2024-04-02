# import media_kit.urls as media_kit_urls
# from action.urls import urlpatterns as action_url_patterns

from django.contrib import admin
# from django.urls import path, re_path
# from django.conf.urls import include

# from rest_framework import routers

# from api import urls as api_urls

# from . import views
# from core import views as core_views


admin.autodiscover()

# router = routers.DefaultRouter()
# router.register(r'user', views.UserViewSet, 'user viewset')

urlpatterns = []
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
