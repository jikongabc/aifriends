# 项目根路由：挂载 admin、web 应用路由，开发态额外托管静态/媒体文件。
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('web.urls')),
]


# 仅限开发阶段使用。生产阶段需要在nginx里配置。
if settings.DEBUG:
    urlpatterns += static(
        '/assets/',
        document_root=settings.BASE_DIR / 'static/frontend/assets'
    )
    urlpatterns += static(
        '/media/',
        document_root=settings.MEDIA_ROOT
    )
