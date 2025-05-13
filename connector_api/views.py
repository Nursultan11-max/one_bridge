# connector_api/views.py

import requests
from requests.auth import HTTPBasicAuth
import logging

from django.conf import settings
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from .models import Product, Order, OrderItem
from .serializers import ProductSerializer, OrderSerializer, OrderItemSerializer

# Настройка логгера
logger = logging.getLogger(__name__)

# ===========================================
# Стандартные ViewSet'ы для CRUD операций
# ===========================================

class ProductViewSet(viewsets.ModelViewSet):
    """
    API эндпоинт для просмотра и редактирования Товаров.
    Предоставляет стандартные CRUD операции.
    """
    queryset = Product.objects.all().order_by('name')
    serializer_class = ProductSerializer
    # Разрешения: Чтение доступно всем, запись - только аутентифицированным.
    # Если глобально в settings.REST_FRAMEWORK установлено IsAuthenticated,
    # то это разрешение будет иметь приоритет для данного ViewSet.
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class OrderViewSet(viewsets.ModelViewSet):
    """
    API эндпоинт для просмотра и редактирования Заказов.
    Предоставляет стандартные CRUD операции.
    Требует аутентификации пользователя.
    """
    queryset = Order.objects.all().order_by('-created_at')
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]


class OrderItemViewSet(viewsets.ModelViewSet):
    """
    API эндпоинт для просмотра и редактирования Позиций Заказа.
    Предоставляет стандартные CRUD операции.
    Требует аутентификации пользователя.
    Примечание: Чаще управление позициями происходит через эндпоинт Заказа.
    """
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemSerializer
    permission_classes = [permissions.IsAuthenticated]

# ===========================================
# ViewSet для операций Интеграции
# ===========================================

class IntegrationViewSet(viewsets.ViewSet):
    """
    ViewSet для операций интеграции с внешними системами.
    Только для администраторов.
    """
    # Доступ к операциям интеграции разрешен только администраторам
    permission_classes = [permissions.IsAdminUser]

    # --- Действие: Синхронизация Товаров из 1С ---
    @action(detail=False, methods=['post'], url_path='sync-products-from-1c')
    def sync_products_from_1c(self, request):
        logger.info("Запуск синхронизации товаров из 1С...")
        products_url = f"{settings.MOCK_1C_BASE_URL}/products"
        auth_1c = HTTPBasicAuth(settings.MOCK_1C_USER, settings.MOCK_1C_PASSWORD)

        created_count = updated_count = errors_count = 0
        error_messages = []

        # Шаг 1: Получение данных из Mock 1C
        try:
            logger.info(f"Запрос товаров из Mock 1C по URL: {products_url}")
            response = requests.get(products_url, auth=auth_1c, timeout=10)
            response.raise_for_status()
            products = response.json()
            logger.info(f"Получено {len(products)} товаров из Mock 1C.")
        except requests.exceptions.Timeout:
            logger.error(f"Таймаут при запросе к Mock 1C: {products_url}")
            return Response({"status": "error", "message": "Ошибка связи с 1С: таймаут."}, status=status.HTTP_504_GATEWAY_TIMEOUT)
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка запроса к Mock 1C: {e}", exc_info=True)
            return Response({"status": "error", "message": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except ValueError as e:
            logger.error(f"Ошибка парсинга JSON от Mock 1C: {e}", exc_info=True)
            return Response({"status": "error", "message": "Некорректный JSON от 1С."}, status=status.HTTP_502_BAD_GATEWAY)

        for prod in products:
            prod_id = prod.get('id', 'N/A')
            try:
                required_keys = ['id', 'name', 'article', 'price', 'stock']
                if not all(k in prod for k in required_keys):
                    errors_count += 1
                    msg = f"Неполные данные для товара ID={prod_id}"
                    error_messages.append(msg)
                    logger.warning(f"Пропуск товара - {msg}: {prod}")
                    continue

                # Подготовка данных для создания/обновления локального товара
                defaults = {
                    'name': prod['name'],
                    'price': prod['price'],
                    'stock_quantity': prod['stock'],
                    'description': prod.get('description', ''),
                    'product_1c_id': prod['id'],
                    'article': prod['article']
                }

                # Использование product_1c_id как уникального ключа для связи
                product, created = Product.objects.update_or_create(
                    article=prod['article'], 
                    defaults=defaults 
                )
                if created:
                    created_count += 1
                    logger.info(f"Создан товар: {product.name} (ID локально: {product.id}, ID 1С: {prod_id})")
                else:
                    updated_count += 1
                    logger.info(f"Обновлен товар: {product.name} (ID локально: {product.id}, ID 1С: {prod_id})")
            except Exception as e:
                errors_count += 1
                msg = f"Ошибка обработки товара ID={prod_id}: {e}"
                error_messages.append(msg)
                logger.error(msg, exc_info=True)

        summary = f"Создано: {created_count}, обновлено: {updated_count}, ошибок: {errors_count}."
        if error_messages:
            logger.warning(f"Ошибки при синхронизации: {error_messages}")

        logger.info(f"Результат синхронизации: {summary}")
        return Response({
            "status": "success",
            "message": summary,
            "details": {
                "created": created_count,
                "updated": updated_count,
                "errors": errors_count,
                "error_list": error_messages
            }
        }, status=status.HTTP_200_OK)

    # --- Действие: Создание Заказа в 1С и локально ---
    @action(detail=False, methods=['post'], url_path='create-order-in-1c')
    def create_order_in_1c(self, request):
        logger.info("Получен запрос на создание заказа в 1С...")
        serializer = OrderSerializer(data=request.data, context={'request': request})
        try:
            serializer.is_valid(raise_exception=True)
            logger.debug(f"Данные заказа валидны: {serializer.validated_data}")
        except ValidationError as e:
            logger.warning(f"Ошибка валидации заказа: {e.detail}")
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)

        validated = serializer.validated_data
        try:
            items = []
            for item in validated.get('items', []):
                prod = item['product']
                prod_id_1c = prod.product_1c_id or prod.article
                if not prod_id_1c:
                    raise ValueError(f"Нет идентификатора 1С для товара {prod.id}")
                items.append({
                    "product_id_1c": prod_id_1c,
                    "quantity": item['quantity'],
                    "price": float(item['price_per_item'])
                })
            payload = {"customer_info": validated.get('customer_info'), "items": items}
            logger.info(f"Payload для 1С: {payload}")
        except Exception as e:
            logger.error(f"Ошибка подготовки данных для 1С: {e}", exc_info=True)
            return Response({"status": "error", "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        orders_url = f"{settings.MOCK_1C_BASE_URL}/orders"
        auth = HTTPBasicAuth(settings.MOCK_1C_USER, settings.MOCK_1C_PASSWORD)
        try:
            logger.info(f"Отправка заказа в 1С по URL: {orders_url}")
            resp = requests.post(orders_url, json=payload, auth=auth, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"Ответ от 1С: {data}")
            if not data.get('success'):
                msg = data.get('message', 'Ошибка 1С')
                logger.warning(f"1С вернула ошибку: {msg}")
                return Response({"status": "error", "message": msg}, status=status.HTTP_400_BAD_REQUEST)
            order_1c_id = data.get('order_1c_id')
            if not order_1c_id:
                logger.error("1С не вернула order_1c_id", exc_info=True)
                return Response({"status": "error", "message": "Нет ID заказа от 1С"}, status=status.HTTP_502_BAD_GATEWAY)
        except requests.exceptions.Timeout:
            logger.error("Таймаут при создании заказа в 1С", exc_info=True)
            return Response({"status": "error", "message": "Таймаут при создании заказа в 1С"}, status=status.HTTP_504_GATEWAY_TIMEOUT)
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка связи с 1С: {e}", exc_info=True)
            return Response({"status": "error", "message": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except ValueError as e:
            logger.error(f"Ошибка парсинга ответа 1С: {e}", exc_info=True)
            return Response({"status": "error", "message": "Некорректный JSON от 1С"}, status=status.HTTP_502_BAD_GATEWAY)

        try:
            context = self.get_serializer_context()
            context['order_1c_id'] = order_1c_id
            save_serializer = OrderSerializer(data=request.data, context=context)
            save_serializer.is_valid(raise_exception=True)
            instance = save_serializer.save()
            logger.info(f"Локальный заказ создан (ID: {instance.id}, 1C ID: {order_1c_id})")
            return Response(save_serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.critical(f"Критическая ошибка при сохранении локального заказа (1C ID: {order_1c_id}): {e}", exc_info=True)
            return Response({
                "status": "critical_error",
                "message": f"Заказ создан в 1С (ID: {order_1c_id}), но не сохранен локально.",
                "order_1c_id": order_1c_id
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # --- Вспомогательные методы (если нужны) ---
    def get_serializer_context(self):
        """Возвращает стандартный контекст для сериализаторов этого ViewSet."""
        return {'request': self.request, 'format': self.format_kwarg, 'view': self}
