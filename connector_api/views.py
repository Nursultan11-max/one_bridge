# connector_api/views.py
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Product, Order, OrderItem
from .serializers import ProductSerializer, OrderSerializer, OrderItemSerializer
import requests
from requests.auth import HTTPBasicAuth
from django.conf import settings

class ProductViewSet(viewsets.ModelViewSet):
    """
    API эндпоинт для просмотра и редактирования товаров.
    """
    queryset = Product.objects.all().order_by('name')
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

class OrderViewSet(viewsets.ModelViewSet):
    """
    API эндпоинт для просмотра и редактирования заказов.
    """
    queryset = Order.objects.all().order_by('-created_at')
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

class OrderItemViewSet(viewsets.ModelViewSet):
    """
    API эндпоинт для просмотра и редактирования позиций заказа.
    Обычно доступ к позициям заказа осуществляется через конкретный заказ (вложенные маршруты),
    но для прямого доступа или администрирования можно создать и такой ViewSet.
    """
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemSerializer
    permission_classes = [permissions.IsAuthenticated]

class IntegrationViewSet(viewsets.ViewSet):
    """
    ViewSet для выполнения операций интеграции, таких как синхронизация данных.
    """
    permission_classes = [permissions.IsAdminUser]

    @action(detail=False, methods=['post'], url_path='sync-products-from-1c')
    def sync_products_from_1c(self, request):
        products_url = f"{settings.MOCK_1C_BASE_URL}/products"
        auth = HTTPBasicAuth(settings.MOCK_1C_USER, settings.MOCK_1C_PASSWORD)

        created_count = 0
        updated_count = 0
        errors_count = 0
        error_messages = []

        try:
            print(f"Django API: Запрос товаров из Mock 1C по URL: {products_url}")
            response_1c = requests.get(products_url, auth=auth, timeout=10)
            response_1c.raise_for_status()

            products_data_1c = response_1c.json()
            print(f"Django API: Получено {len(products_data_1c)} товаров из Mock 1C.")

            for prod_1c in products_data_1c:
                try:
                    if not all(k in prod_1c for k in ['id', 'name', 'article', 'price', 'stock']):
                        error_messages.append(f"Неполные данные для товара: {prod_1c.get('id', 'N/A')}")
                        errors_count += 1
                        continue

                    defaults = {
                        'name': prod_1c['name'],
                        'price': prod_1c['price'],
                        'stock_quantity': prod_1c['stock'],
                        'description': prod_1c.get('description', ''),
                        'product_1c_id': prod_1c['id'],
                        'article': prod_1c['article']
                    }

                    product, created = Product.objects.update_or_create(
                        product_1c_id=prod_1c['id'],
                        defaults=defaults
                    )

                    if created:
                        created_count += 1
                        print(f"Создан товар: {product.name}")
                    else:
                        updated_count += 1
                        print(f"Обновлен товар: {product.name}")

                except Exception as e_item:
                    errors_count += 1
                    error_messages.append(f"Ошибка товара {prod_1c.get('id', 'N/A')}: {str(e_item)}")

        except requests.exceptions.RequestException as e_req:
            return Response(
                {"status": "error", "message": f"Ошибка запроса к 1С: {str(e_req)}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except ValueError as e_json:
            return Response(
                {"status": "error", "message": f"Ошибка JSON от 1С: {str(e_json)}"},
                status=status.HTTP_502_BAD_GATEWAY
            )

        summary_message = (
            f"Создано: {created_count}, Обновлено: {updated_count}, Ошибок: {errors_count}."
        )
        if error_messages:
            summary_message += " Ошибки: " + "; ".join(error_messages)

        return Response(
            {
                "status": "success",
                "message": summary_message,
                "created": created_count,
                "updated": updated_count,
                "errors": errors_count,
                "error_details": error_messages
            },
            status=status.HTTP_200_OK
        )
