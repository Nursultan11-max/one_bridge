from rest_framework import serializers
from .models import Product, Order, OrderItem

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = '__all__' # Включаем все поля модели
        # Или можно указать конкретные поля:
        # fields = ['id', 'product_1c_id', 'name', 'article', 'description', 'price', 'stock_quantity', 'created_at', 'updated_at']

class OrderItemSerializer(serializers.ModelSerializer):
    # Если хотим видеть не просто ID товара, а какую-то информацию о нем
    # product_name = serializers.CharField(source='product.name', read_only=True) # Пример
    # product_article = serializers.CharField(source='product.article', read_only=True) # Пример

    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'quantity', 'price_per_item', 'total_price'] # 'order' обычно не включаем сюда, т.к. он будет вложенным в OrderSerializer
        read_only_fields = ['total_price'] # total_price - это свойство, оно только для чтения

class OrderSerializer(serializers.ModelSerializer):
    # Включаем связанные позиции заказа (OrderItems) прямо в сериализатор Заказа
    # Это называется вложенными сериализаторами (nested serializers)
    items = OrderItemSerializer(many=True, read_only=False) # read_only=False если хотим иметь возможность создавать/обновлять заказ с позициями

    # Если хотим отображать не просто ID статуса, а его читаемое значение
    order_status_display = serializers.CharField(source='get_order_status_display', read_only=True)

    class Meta:
        model = Order
        fields = [
            'id',
            'order_1c_id',
            'customer_info',
            'order_status',
            'order_status_display', # Отображаемое значение статуса
            'total_amount',
            'created_at',
            'updated_at',
            'items' # Вложенные позиции заказа
        ]
        read_only_fields = ['total_amount'] # Предположим, что total_amount будет рассчитываться на основе items или обновляться отдельно

    # Для создания заказа вместе с его позициями (create with nested writable serializers)
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        order = Order.objects.create(**validated_data)
        for item_data in items_data:
            OrderItem.objects.create(order=order, **item_data)
        # Здесь можно добавить логику для пересчета order.total_amount на основе созданных items
        # Например: order.total_amount = sum(item.total_price for item in order.items.all())
        # order.save()
        return order

    # Для обновления заказа вместе с его позициями (update with nested writable serializers)
    # Это более сложная логика, так как нужно обрабатывать существующие, новые и удаляемые позиции.
    # Для MVP можно пока не реализовывать сложный update для вложенных items,
    # или обновлять items через отдельные эндпоинты.
    # Если очень нужно, то можно реализовать так:
    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None) # items может не быть при частичном обновлении

        # Обновляем поля самого заказа
        instance.customer_info = validated_data.get('customer_info', instance.customer_info)
        instance.order_status = validated_data.get('order_status', instance.order_status)
        # ... другие поля заказа
        instance.save()

        if items_data is not None:
            # Простая реализация: удаляем старые и создаем новые (не очень эффективно, но просто)
            # Более сложная - сопоставлять существующие items, обновлять их, удалять лишние и создавать новые.
            instance.items.all().delete()
            for item_data in items_data:
                OrderItem.objects.create(order=instance, **item_data)
            # Здесь также можно пересчитать instance.total_amount
            # instance.total_amount = sum(item.total_price for item in instance.items.all())
            # instance.save()

        return instance