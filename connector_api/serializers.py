import logging
from rest_framework import serializers
from django.db import transaction
from decimal import Decimal
from .models import Product, Order, OrderItem

# Настройка логгера
logger = logging.getLogger(__name__)

# --- Сериализатор для Товаров ---
class ProductSerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели Product.
    Используется для преобразования данных товара между Python объектами и JSON.
    """
    class Meta:
        model = Product
        # fields = '__all__' # Простой вариант: включаем все поля модели
        # Явное перечисление полей более безопасно и читаемо:
        fields = [
            'id',
            'product_1c_id',
            'name',
            'article',
            'description',
            'price',
            'stock_quantity',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

# --- Сериализатор для Позиций Заказа ---
class OrderItemSerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели OrderItem.
    Используется для представления позиций внутри заказа.
    """
    # Для вывода можно добавить информацию о товаре, если нужно
    # product_name = serializers.CharField(source='product.name', read_only=True)
    # product_article = serializers.CharField(source='product.article', read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            'id',
            'product',
            'quantity',
            'price_per_item',
            'total_price'
        ]
        read_only_fields = ['id', 'total_price']

# --- Сериализатор для Заказов ---
class OrderSerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели Order.
    Поддерживает вложенное создание и чтение позиций заказа.
    Рассчитывает общую сумму заказа при создании/обновлении.
    """
    items = OrderItemSerializer(many=True)
    order_status_display = serializers.CharField(source='get_order_status_display', read_only=True)

    class Meta:
        model = Order
        fields = [
            'id',
            'order_1c_id',
            'customer_info',
            'order_status',
            'order_status_display',
            'total_amount',
            'created_at',
            'updated_at',
            'items'
        ]
        read_only_fields = ['id', 'total_amount', 'created_at', 'updated_at', 'order_status_display']

    @transaction.atomic
    def create(self, validated_data):
        logger.info("Начало создания заказа.")
        items_data = validated_data.pop('items')
        order_1c_id_from_view = self.context.get('order_1c_id')
        try:
            order = Order.objects.create(**validated_data)
            if order_1c_id_from_view:
                order.order_1c_id = order_1c_id_from_view
            total_amount_calculated = Decimal('0.00')
            for item_data in items_data:
                order_item = OrderItem.objects.create(order=order, **item_data)
                total_amount_calculated += order_item.total_price
            order.total_amount = total_amount_calculated
            order.save()
            logger.info(f"Заказ создан успешно: ID={order.id}, total_amount={order.total_amount}")
            return order
        except Exception as e:
            logger.error(f"Ошибка при создании заказа: {e}", exc_info=True)
            raise

    @transaction.atomic
    def update(self, instance, validated_data):
        logger.info(f"Начало обновления заказа: ID={instance.id}")
        items_data = validated_data.pop('items', None)
        try:
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            if items_data is not None:
                instance.items.all().delete()
                for item_data in items_data:
                    OrderItem.objects.create(order=instance, **item_data)
            total_amount_calculated = Decimal('0.00')
            for item in instance.items.all():
                total_amount_calculated += item.total_price
            instance.total_amount = total_amount_calculated
            instance.save()
            logger.info(f"Заказ обновлен успешно: ID={instance.id}, total_amount={instance.total_amount}")
            return instance
        except Exception as e:
            logger.error(f"Ошибка при обновлении заказа ID={instance.id}: {e}", exc_info=True)
            raise

    # Добавляем валидацию для примера: количество должно быть > 0
    def validate_items(self, items_data):
        logger.debug(f"Валидация позиций заказа: {len(items_data) if items_data else 0} позиций")
        if not items_data:
            logger.warning("Валидация заказа: нет позиций в заказе.")
            raise serializers.ValidationError("Заказ должен содержать хотя бы одну позицию.")
        for item_data in items_data:
            if item_data['quantity'] <= 0:
                logger.warning(f"Валидация заказа: неверное количество для товара ID={item_data.get('product')}: {item_data['quantity']}")
                raise serializers.ValidationError(f"Количество для товара '{item_data['product']}' должно быть больше нуля.")
        return items_data
