from django.db import models
from django.utils import timezone # Для установки времени по умолчанию

# Модель для Товаров
class Product(models.Model):
    # product_id = models.AutoField(primary_key=True) # Django автоматически создает id, если не указано другое PK
    product_1c_id = models.CharField(max_length=255, unique=True, null=True, blank=True, verbose_name="ID товара в 1С")
    name = models.CharField(max_length=500, verbose_name="Наименование товара")
    article = models.CharField(max_length=100, unique=True, null=True, blank=True, verbose_name="Артикул")
    description = models.TextField(null=True, blank=True, verbose_name="Описание товара")
    price = models.DecimalField(max_digits=18, decimal_places=2, default=0.00, verbose_name="Цена")
    stock_quantity = models.IntegerField(default=0, verbose_name="Количество на складе")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Дата создания") # Используем timezone.now для корректной работы с часовыми поясами
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления") # auto_now обновляется при каждом сохранении

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        ordering = ['name'] # Сортировка по умолчанию в админке и запросах

    def __str__(self):
        return f"{self.name} (Арт: {self.article or 'N/A'})"

# Модель для Заказов
class Order(models.Model):
    # order_id = models.AutoField(primary_key=True)
    order_1c_id = models.CharField(max_length=255, unique=True, null=True, blank=True, verbose_name="ID заказа в 1С")
    customer_info = models.TextField(null=True, blank=True, verbose_name="Информация о клиенте")

    # Статусы заказа можно вынести в Choices для удобства
    class OrderStatus(models.TextChoices):
        NEW = 'NEW', 'Новый'
        PROCESSING = 'PROCESSING', 'В обработке'
        SHIPPED = 'SHIPPED', 'Отгружен'
        DELIVERED = 'DELIVERED', 'Доставлен'
        CANCELED = 'CANCELED', 'Отменен'

    order_status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.NEW,
        verbose_name="Статус заказа"
    )
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0.00, verbose_name="Общая сумма заказа")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        ordering = ['-created_at'] # Сортировка по умолчанию - сначала новые

    def __str__(self):
        return f"Заказ №{self.id} от {self.created_at.strftime('%Y-%m-%d %H:%M')} (Статус: {self.get_order_status_display()})"

# Модель для Позиций Заказа
class OrderItem(models.Model):
    # order_item_id = models.AutoField(primary_key=True)
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE, verbose_name="Заказ")
    product = models.ForeignKey(Product, related_name='order_items', on_delete=models.PROTECT, verbose_name="Товар") # PROTECT, чтобы не удалить товар, если он есть в заказах
    quantity = models.PositiveIntegerField(verbose_name="Количество")
    price_per_item = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Цена за единицу на момент заказа")

    class Meta:
        verbose_name = "Позиция заказа"
        verbose_name_plural = "Позиции заказа"
        unique_together = ('order', 'product') # Гарантирует, что один и тот же товар не будет добавлен в один заказ дважды как отдельная позиция

    def __str__(self):
        return f"{self.quantity} x {self.product.name} в Заказе №{self.order.id}"

    @property
    def total_price(self):
        return self.quantity * self.price_per_item