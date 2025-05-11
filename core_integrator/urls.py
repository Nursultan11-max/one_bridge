"""
URL configuration for core_integrator project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include # Убедитесь, что include импортирован

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('connector_api.urls')), # Подключаем URL-ы нашего приложения connector_api
    # 'api/v1/' - это хороший префикс для версионирования вашего API
]