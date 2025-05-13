# connector_api/views.py

import requests
from requests.auth import HTTPBasicAuth
import logging # Лучше использовать logging вместо print в реальных приложениях

from django.conf import settings
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError # Для явного импорта

from .models import Product, Order, OrderItem
from .serializers import ProductSerializer, OrderSerializer, OrderItemSerializer

# Настройка логгера (лучше, чем print)
# В реальном проекте логгер настраивается в settings.py
logger = logging.getLogger(__name__)
# Для простоты в дипломной работе можно оставить print или использовать базовый logging
# logging.basicConfig(level=logging.INFO) # Простейшая конфигурация

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
    ViewSet для выполнения специфических операций интеграции с внешними системами (например, 1С).
    Эндпоинты в этом ViewSet не привязаны к конкретной модели через queryset,
    а реализуют кастомную логику взаимодействия.
    """
    # Доступ к операциям интеграции разрешен только администраторам
    permission_classes = [permissions.IsAdminUser]

    # --- Действие: Синхронизация Товаров из 1С ---
    @action(detail=False, methods=['post'], url_path='sync-products-from-1c')
    def sync_products_from_1c(self, request):
        """
        Инициирует процесс синхронизации товаров.
        1. Запрашивает список товаров из Mock 1C API.
        2. Обновляет или создает соответствующие товары в локальной базе данных (MS SQL).
        Возвращает отчет о результатах синхронизации.
        """
        logger.info("Django API: Запуск синхронизации товаров из 1С...") # Используем logger
        products_url = f"{settings.MOCK_1C_BASE_URL}/products"
        auth_1c = HTTPBasicAuth(settings.MOCK_1C_USER, settings.MOCK_1C_PASSWORD)

        created_count = 0
        updated_count = 0
        errors_count = 0
        error_messages = []

        # Шаг 1: Получение данных из Mock 1C
        try:
            logger.info(f"Django API: Запрос товаров из Mock 1C по URL: {products_url}")
            response_1c = requests.get(products_url, auth=auth_1c, timeout=10) # Таймаут 10 секунд
            response_1c.raise_for_status() # Проверка на HTTP ошибки (4xx, 5xx)

            products_data_1c = response_1c.json()
            logger.info(f"Django API: Получено {len(products_data_1c)} товаров из Mock 1C.")

        except requests.exceptions.Timeout:
            logger.error(f"Django API: Ошибка запроса к Mock 1C: таймаут соединения ({products_url})")
            return Response(
                {"status": "error", "message": "Ошибка связи с сервисом 1С: Превышено время ожидания ответа."},
                status=status.HTTP_504_GATEWAY_TIMEOUT
            )
        except requests.exceptions.RequestException as e_req:
            logger.error(f"Django API: Ошибка запроса к Mock 1C: {e_req}")
            return Response(
                {"status": "error", "message": f"Ошибка связи с сервисом 1С: {str(e_req)}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE # Сервис 1С недоступен
            )
        except ValueError as e_json: # Ошибка парсинга JSON
            logger.error(f"Django API: Ошибка парсинга JSON ответа от Mock 1C: {e_json}")
            return Response(
                {"status": "error", "message": f"Некорректный формат ответа от сервиса 1С: {str(e_json)}"},
                status=status.HTTP_502_BAD_GATEWAY # Ответ от шлюза/сервера некорректен
            )

        # Шаг 2: Обработка и сохранение данных в локальной БД
        for prod_1c in products_data_1c:
            item_id_for_log = prod_1c.get('id', 'N/A') # ID для логов
            try:
                # Проверка наличия обязательных полей в ответе от 1С
                required_keys = ['id', 'name', 'article', 'price', 'stock']
                if not all(k in prod_1c for k in required_keys):
                    error_msg = f"Неполные данные для товара ID={item_id_for_log}"
                    error_messages.append(error_msg)
                    errors_count += 1
                    logger.warning(f"Django API: Пропуск товара - {error_msg}. Данные: {prod_1c}")
                    continue

                # Подготовка данных для создания/обновления локального товара
                defaults = {
                    'name': prod_1c['name'],
                    'price': prod_1c['price'], # Убедитесь, что тип совместим (DecimalField примет число или строку)
                    'stock_quantity': prod_1c['stock'],
                    'description': prod_1c.get('description', ''), # Используем get для опционального поля
                    'product_1c_id': prod_1c['id'], # Сохраняем ID из 1С
                    'article': prod_1c['article'] # Сохраняем/обновляем артикул
                }

                # Использование product_1c_id как уникального ключа для связи
                product, created = Product.objects.update_or_create(
                    article=prod_1c['article'], # Артикул как дополнительный уникальный ключ
                    defaults=defaults # Поля для обновления/установки при создании
                )

                if created:
                    created_count += 1
                    logger.info(f"Django API: Создан товар: {product.name} (ID: {product.id}, 1C ID: {prod_1c['id']})")
                else:
                    updated_count += 1
                    logger.info(f"Django API: Обновлен товар: {product.name} (ID: {product.id}, 1C ID: {prod_1c['id']})")

            except Exception as e_item: # Ловим другие возможные ошибки (например, БД)
                errors_count += 1
                error_msg = f"Ошибка обработки товара ID={item_id_for_log}: {str(e_item)}"
                error_messages.append(error_msg)
                logger.error(f"Django API: {error_msg}. Данные: {prod_1c}")

        # Шаг 3: Формирование ответа
        summary_message = (
            f"Синхронизация товаров завершена. "
            f"Создано: {created_count}, Обновлено: {updated_count}, Ошибок: {errors_count}."
        )
        if error_messages:
            # Не добавляем все детали в общий message, если их много, но сохраняем в error_details
             logger.warning(f"Django API: Во время синхронизации товаров произошли ошибки: {error_messages}")

        logger.info(f"Django API: Результат синхронизации: {summary_message}")
        return Response(
            {
                "status": "success",
                "message": summary_message,
                "details": { # Более структурированный ответ
                    "created": created_count,
                    "updated": updated_count,
                    "errors": errors_count,
                    "error_list": error_messages # Список конкретных ошибок
                }
            },
            status=status.HTTP_200_OK
        )

    # --- Действие: Создание Заказа в 1С и локально ---
    @action(detail=False, methods=['post'], url_path='create-order-in-1c')
    def create_order_in_1c(self, request):
        """
        Принимает данные нового заказа от внешней системы (например, E-commerce).
        1. Валидирует входящие данные.
        2. Подготавливает и отправляет данные заказа в Mock 1C API.
        3. Обрабатывает ответ от Mock 1C (получает ID заказа в 1С).
        4. Сохраняет заказ и его позиции в локальной базе данных (MS SQL).
        Возвращает данные созданного локально заказа или сообщение об ошибке.
        """
        logger.info("Django API: Получен запрос на создание заказа в 1С...")

        # Шаг 1: Валидация входящих данных с помощью OrderSerializer
        # Передаем request=request в контекст, если сериализатору нужен доступ к запросу
        serializer = OrderSerializer(data=request.data, context={'request': request})
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            logger.warning(f"Django API: Ошибка валидации входящих данных заказа: {e.detail}")
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data
        logger.info(f"Django API: Входящие данные заказа валидны.")

        # Шаг 2: Подготовка данных для отправки в Mock 1C
        try:
            items_payload_1c = []
            for item_data in validated_data.get('items', []):
                product_instance = item_data['product'] # Объект Product после валидации
                # Идентификатор товара для 1С (предпочитаем ID 1С, если нет - артикул)
                product_identifier_1c = product_instance.product_1c_id or product_instance.article
                print(f"DEBUG: Продукт {product_instance.id}, product_1c_id={product_instance.product_1c_id}, article={product_instance.article}")

                if not product_identifier_1c:
                    # Если нет идентификатора 1С, интеграция невозможна
                    raise ValueError(f"Невозможно идентифицировать товар '{product_instance.name}' (ID: {product_instance.id}) для системы 1С (отсутствует ID 1С и артикул).")

                items_payload_1c.append({
                    "product_id_1c": product_identifier_1c,
                    "quantity": item_data['quantity'],
                    "price": float(item_data['price_per_item']) # Преобразуем Decimal в float для JSON/1C
                })

            payload_1c = {
                "customer_info": validated_data.get('customer_info'),
                "items": items_payload_1c,
                # Добавляем ID нашего будущего заказа, если 1С может его использовать для связи
                # "external_order_id": str(uuid.uuid4()) # Пример
            }
            logger.info(f"Django API: Данные для Mock 1C подготовлены: {payload_1c}")

        except Exception as e_prepare:
            logger.error(f"Django API: Ошибка подготовки данных для отправки в 1С: {e_prepare}")
            return Response(
                {"status": "error", "message": f"Ошибка подготовки данных для 1С: {str(e_prepare)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Шаг 3: Отправка данных в Mock 1C
        orders_url_1c = f"{settings.MOCK_1C_BASE_URL}/orders"
        auth_1c = HTTPBasicAuth(settings.MOCK_1C_USER, settings.MOCK_1C_PASSWORD)
        order_1c_id = None # Инициализируем переменную

        try:
            logger.info(f"Django API: Отправка заказа в Mock 1C по URL: {orders_url_1c}")
            response_1c = requests.post(orders_url_1c, json=payload_1c, auth=auth_1c, timeout=15) # Таймаут 15 секунд
            response_1c.raise_for_status() # Проверка на HTTP ошибки

            response_data_1c = response_1c.json()
            logger.info(f"Django API: Получен ответ от Mock 1C: {response_data_1c}")

            # Проверка ответа от Mock 1C
            if not response_data_1c.get('success'):
                error_message_1c = response_data_1c.get('message', 'Неизвестная ошибка от 1С')
                logger.warning(f"Django API: Mock 1C вернул ошибку: {error_message_1c}")
                # При ошибке от 1С НЕ сохраняем заказ локально
                return Response(
                    {"status": "error", "message": f"Ошибка от сервиса 1С: {error_message_1c}"},
                    status=status.HTTP_400_BAD_REQUEST # Ошибка в бизнес-логике 1С
                )

            order_1c_id = response_data_1c.get('order_1c_id')
            if not order_1c_id:
                logger.error("Django API: Ошибка! Mock 1C вернул success=true, но не предоставил order_1c_id.")
                # Не сохраняем локально, если нет ID от 1С
                return Response(
                    {"status": "error", "message": "Сервис 1С подтвердил успех, но не вернул ID созданного заказа."},
                    status=status.HTTP_502_BAD_GATEWAY
                )

            logger.info(f"Django API: Заказ успешно обработан Mock 1C. ID заказа в 1С: {order_1c_id}")

        except requests.exceptions.Timeout:
            logger.error(f"Django API: Ошибка связи с Mock 1C: таймаут ({orders_url_1c})")
            # НЕ сохраняем заказ локально
            return Response(
                {"status": "error", "message": "Ошибка связи с сервисом 1С: Превышено время ожидания ответа при создании заказа."},
                status=status.HTTP_504_GATEWAY_TIMEOUT
            )
        except requests.exceptions.RequestException as e_req:
            logger.error(f"Django API: Ошибка связи с Mock 1C: {e_req}")
            # НЕ сохраняем заказ локально
            return Response(
                {"status": "error", "message": f"Ошибка связи с сервисом 1С при создании заказа: {str(e_req)}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except ValueError as e_json: # Ошибка парсинга JSON ответа 1С
            logger.error(f"Django API: Ошибка парсинга JSON ответа от Mock 1C: {e_json}")
            return Response(
                 {"status": "error", "message": f"Некорректный формат ответа от сервиса 1С при создании заказа: {str(e_json)}"},
                 status=status.HTTP_502_BAD_GATEWAY
            )

        # Шаг 4: Сохранение заказа локально (только если в 1С все успешно и получен ID)
        try:
            # Используем тот же инстанс сериализатора, который прошел валидацию
            # Передаем ID из 1С через контекст сериализатора
            context_data = self.get_serializer_context() # Получаем базовый контекст (включая request)
            context_data['order_1c_id'] = order_1c_id    # Добавляем наш ID

            # Вызываем save() у исходного сериализатора, передавая контекст
            serializer = OrderSerializer(data=request.data, context=context_data)
            serializer.is_valid(raise_exception=True)
            instance = serializer.save()

            print(f"DEBUG: После вызова serializer.save. ID инстанса: {instance.id}, order_1c_id инстанса: {instance.order_1c_id}")

            # Возвращаем данные созданного локально объекта (сериализатор уже обновился инстансом)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e_save:
            # КРИТИЧЕСКАЯ ОШИБКА: Заказ создан в 1С, но не сохранен локально!
            logger.critical(f"Django API: КРИТИЧЕСКАЯ ОШИБКА! Заказ создан в 1С (1C ID: {order_1c_id}), но не удалось сохранить локально: {e_save}", exc_info=True)
            # Возвращаем ошибку сервера, но сообщаем ID из 1С для ручного разбирательства
            return Response(
                {
                    "status": "critical_error",
                    "message": f"Заказ успешно создан в системе 1С (ID: {order_1c_id}), но произошла внутренняя ошибка при сохранении заказа в локальной системе. Пожалуйста, обратитесь к системному администратору.",
                    "order_1c_id": order_1c_id
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    # --- Вспомогательные методы (если нужны) ---
    def get_serializer_context(self):
        """Возвращает стандартный контекст для сериализаторов этого ViewSet."""
        return {'request': self.request, 'format': self.format_kwarg, 'view': self}