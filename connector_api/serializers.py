# connector_api/serializers.py

from rest_framework import serializers
from django.db import transaction # Импортируем для атомарных транзакций
from decimal import Decimal # Импортируем для точных денежных расчетов
from .models import Product, Order, OrderItem

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
        read_only_fields = ['id', 'created_at', 'updated_at'] # Явно укажем read-only поля

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
            'product', # При вводе ожидается ID товара, при выводе может быть ID или вложенный объект (зависит от depth)
            'quantity',
            'price_per_item',
            'total_price' # Наше свойство @property из модели
        ]
        read_only_fields = ['id', 'total_price'] # ID и вычисляемое поле только для чтения

# --- Сериализатор для Заказов ---
class OrderSerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели Order.
    Поддерживает вложенное создание и чтение позиций заказа (OrderItems).
    Рассчитывает общую сумму заказа при создании/обновлении.
    """
    # Вложенный сериализатор для позиций заказа
    items = OrderItemSerializer(many=True) # read_only=False по умолчанию, позволяет записывать

    # Добавляем читаемое значение статуса для удобства фронтенда/клиента
    order_status_display = serializers.CharField(source='get_order_status_display', read_only=True)

    class Meta:
        model = Order
        fields = [
            'id',
            'order_1c_id',
            'customer_info',
            'order_status',
            'order_status_display',
            'total_amount', # Будет рассчитываться автоматически
            'created_at',
            'updated_at',
            'items' # Вложенные позиции
        ]
        # order_1c_id может быть установлен при создании через view, total_amount рассчитывается
        read_only_fields = ['id', 'total_amount', 'created_at', 'updated_at', 'order_status_display']

    @transaction.atomic # Гарантируем, что создание заказа и его позиций будет атомарной операцией
    def create(self, validated_data):
        """
        Создает новый заказ вместе с его позициями.
        Рассчитывает total_amount.
        Принимает и сохраняет order_1c_id, если он передан из view при вызове save().
        """
        items_data = validated_data.pop('items')
        # Получаем order_1c_id, если он был передан в save() из view
        # (validated_data в create не содержит read_only поля, поэтому нужно передавать через save)
        order_1c_id_from_view = self.context.get('order_1c_id', None) # Лучше передавать через context

        # Создаем сам заказ без items
        order = Order.objects.create(**validated_data)

        # Присваиваем order_1c_id, если он был получен извне (например, от 1С)
        if order_1c_id_from_view:
            order.order_1c_id = order_1c_id_from_view
            # validated_data уже не содержит order_1c_id

        total_amount_calculated = Decimal('0.00')
        # Создаем связанные позиции заказа
        for item_data in items_data:
            # Создаем позицию и сразу считаем ее стоимость
            order_item = OrderItem.objects.create(order=order, **item_data)
            # Используем свойство модели или считаем вручную для точности
            total_amount_calculated += order_item.total_price
            # или total_amount_calculated += (Decimal(item_data['quantity']) * Decimal(item_data['price_per_item']))


        # Обновляем общую сумму заказа и сохраняем все изменения (включая order_1c_id)
        order.total_amount = total_amount_calculated
        order.save()

        return order

    @transaction.atomic # Гарантируем атомарность обновления
    def update(self, instance, validated_data):
        """
        Обновляет заказ. Поддерживает обновление вложенных позиций
        по принципу "удалить старые, создать новые".
        Пересчитывает total_amount.
        """
        items_data = validated_data.pop('items', None) # items может не быть при частичном обновлении (PATCH)

        # Обновляем основные поля заказа
        # Используем setattr для обновления полей из validated_data
        # Это удобнее, чем перечислять каждое поле вручную
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        # instance.customer_info = validated_data.get('customer_info', instance.customer_info) # Старый вариант
        # instance.order_status = validated_data.get('order_status', instance.order_status) # Старый вариант

        # Если данные для items были переданы, обновляем их
        if items_data is not None:
            # Простая стратегия: удалить все существующие и создать новые
            instance.items.all().delete()
            for item_data in items_data:
                OrderItem.objects.create(order=instance, **item_data)

        # Пересчитываем total_amount на основе ИТОГОВОГО набора позиций
        total_amount_calculated = Decimal('0.00')
        # Обязательно перезапрашиваем instance.items.all() после возможных изменений
        for item in instance.items.all():
            total_amount_calculated += item.total_price

        instance.total_amount = total_amount_calculated
        instance.save() # Сохраняем все изменения заказа

        return instance

    # Добавляем валидацию для примера: количество должно быть > 0
    def validate_items(self, items_data):
        """
        Проверяет, что в заказе есть хотя бы одна позиция,
        и что количество в каждой позиции > 0.
        """
        if not items_data:
            raise serializers.ValidationError("Заказ должен содержать хотя бы одну позицию.")
        for item_data in items_data:
            if item_data['quantity'] <= 0:
                raise serializers.ValidationError(f"Количество для товара '{item_data['product']}' должно быть больше нуля.")
        return items_data