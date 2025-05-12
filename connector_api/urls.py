# connector_api/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProductViewSet, OrderViewSet, OrderItemViewSet, IntegrationViewSet # Добавляем IntegrationViewSet

# Создаем router и регистрируем наши ViewSet'ы
router = DefaultRouter()
router.register(r'products', ProductViewSet, basename='product')
router.register(r'orders', OrderViewSet, basename='order')
router.register(r'order-items', OrderItemViewSet, basename='orderitem')
router.register(r'integration', IntegrationViewSet, basename='integration') # Регистрируем новый ViewSet

# API URL-ы теперь автоматически генерируются роутером.
urlpatterns = [
    path('', include(router.urls)),
]