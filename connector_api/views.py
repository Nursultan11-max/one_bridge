from rest_framework import viewsets, permissions
from .models import Product, Order, OrderItem
from .serializers import ProductSerializer, OrderSerializer, OrderItemSerializer

class ProductViewSet(viewsets.ModelViewSet):
    """
    API эндпоинт для просмотра и редактирования товаров.
    """
    queryset = Product.objects.all().order_by('name')
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly] # Пример: аутентифицированные могут все, остальные - только чтение
    # Для более строгих прав: permission_classes = [permissions.IsAuthenticated]

class OrderViewSet(viewsets.ModelViewSet):
    """
    API эндпоинт для просмотра и редактирования заказов.
    """
    queryset = Order.objects.all().order_by('-created_at')
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated] # Заказы обычно требуют аутентификации

    # Если нужно фильтровать заказы по текущему пользователю (пример, если у заказов есть связь с User)
    # def get_queryset(self):
    #     user = self.request.user
    #     if user.is_staff: # Администраторы видят все заказы
    #         return Order.objects.all()
    #     return Order.objects.filter(user=user) # Обычные пользователи видят только свои заказы

class OrderItemViewSet(viewsets.ModelViewSet):
    """
    API эндпоинт для просмотра и редактирования позиций заказа.
    Обычно доступ к позициям заказа осуществляется через конкретный заказ (вложенные маршруты),
    но для прямого доступа или администрирования можно создать и такой ViewSet.
    """
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemSerializer
    permission_classes = [permissions.IsAuthenticated] # Позиции заказа также требуют аутентификации