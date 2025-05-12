from fastapi import FastAPI, HTTPException, Body, Header, status
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import uuid # Для генерации фейковых ID заказов

# --- Модели данных (Pydantic) для запросов и ответов ---

class MockProduct(BaseModel):
    id: str # UUID или другой уникальный строковый ID из "1С"
    name: str
    article: str
    price: float
    stock: int
    description: Optional[str] = None

class MockOrderItem(BaseModel):
    product_id_1c: str # ID товара из "1С"
    quantity: int
    price: float # Цена за единицу на момент заказа в "1С"

class MockOrderPayload(BaseModel):
    customer_info: Optional[str] = None
    items: List[MockOrderItem]
    # Дополнительные поля, которые может присылать Django API
    external_order_id: Optional[str] = None # ID заказа из внешней системы (Django API)

class MockOrderResponse(BaseModel):
    success: bool
    order_1c_id: Optional[str] = None
    message: Optional[str] = None

# --- Создание FastAPI приложения ---
app = FastAPI(title="Mock 1C HTTP-Service")

# --- Фейковая "база данных" товаров в памяти ---
# В реальной 1С это были бы данные из справочников и регистров
mock_products_db: List[MockProduct] = [
    MockProduct(id=str(uuid.uuid4()), name="Хлеб Бородинский", article="ХЛ001", price=50.00, stock=100, description="Классический ржаной хлеб"),
    MockProduct(id=str(uuid.uuid4()), name="Молоко Простоквашино 3.2%", article="МЛ005", price=85.50, stock=200, description="Пастеризованное молоко"),
    MockProduct(id=str(uuid.uuid4()), name="Сыр Российский", article="СР012", price=650.00, stock=50, description="Полутвердый сыр, кг"),
    MockProduct(id=str(uuid.uuid4()), name="Кофе растворимый Якобс Монарх", article="КФ003", price=350.00, stock=80, description="100г, стеклянная банка"),
]

# --- Фейковая "база данных" созданных заказов в памяти ---
mock_orders_created: List[Dict[str, Any]] = []


# --- Аутентификация (имитация Basic Auth, как может быть в 1С) ---
# Предположим, 1С ожидает определенный логин/пароль
MOCK_1C_USER = "user1c"
MOCK_1C_PASSWORD = "password1c"

async def verify_basic_auth(authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Basic"},
        )
    try:
        # Basic base64(username:password)
        import base64
        scheme, _, credentials = authorization.partition(' ')
        if scheme.lower() != 'basic':
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication scheme",
                headers={"WWW-Authenticate": "Basic"},
            )
        decoded_credentials = base64.b64decode(credentials).decode("utf-8")
        username, _, password = decoded_credentials.partition(':')

        if username != MOCK_1C_USER or password != MOCK_1C_PASSWORD:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid username or password",
            )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    print(f"Mock 1C: Basic Auth successful for user {username}")

# --- Эндпоинты Mock-сервера ---

@app.get("/1c_mock/hs/exchange/products", response_model=List[MockProduct])
async def get_products(authorization: Optional[str] = Header(None)):
    """
    Имитация HTTP-сервиса 1С для выгрузки списка товаров.
    Требует Basic Auth.
    """
    await verify_basic_auth(authorization) # Проверка аутентификации
    print(f"Mock 1C: GET /products - Выгружено {len(mock_products_db)} товаров.")
    return mock_products_db

@app.post("/1c_mock/hs/exchange/orders", response_model=MockOrderResponse)
async def create_order(
    order_data: MockOrderPayload,
    authorization: Optional[str] = Header(None)
):
    """
    Имитация HTTP-сервиса 1С для создания нового заказа.
    Требует Basic Auth.
    """
    await verify_basic_auth(authorization) # Проверка аутентификации

    print(f"Mock 1C: POST /orders - Получены данные для нового заказа: {order_data.dict()}")

    # Имитация проверки товаров из заказа по "базе данных" товаров
    for item in order_data.items:
        found_product = next((p for p in mock_products_db if p.id == item.product_id_1c or p.article == item.product_id_1c), None)
        if not found_product:
            print(f"Mock 1C: Ошибка! Товар с ID/Артикулом '{item.product_id_1c}' не найден в базе 1С.")
            return MockOrderResponse(success=False, message=f"Товар с ID/Артикулом '{item.product_id_1c}' не найден.")
        # Можно добавить имитацию проверки остатков, если нужно
        # if found_product.stock < item.quantity:
        #     return MockOrderResponse(success=False, message=f"Недостаточно товара '{found_product.name}' на складе.")

    # Имитация создания заказа в "1С"
    new_order_1c_id = f"ЗАКАЗ-{str(uuid.uuid4())[:8].upper()}"
    created_order_info = {
        "order_1c_id": new_order_1c_id,
        "data_received": order_data.dict(),
        "status_1c": "Принят (имитация)"
    }
    mock_orders_created.append(created_order_info)

    print(f"Mock 1C: Заказ успешно 'создан' в 1С. ID заказа в 1С: {new_order_1c_id}")
    return MockOrderResponse(success=True, order_1c_id=new_order_1c_id, message="Заказ успешно принят в обработку (имитация).")

@app.get("/")
async def root():
    return {"message": "Mock 1C HTTP-Service is running. Доступные эндпоинты: /1c_mock/hs/exchange/products, /1c_mock/hs/exchange/orders"}

# --- Запуск сервера (если файл запускается напрямую) ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001) # Запускаем на порту 8001, чтобы не конфликтовать с Django (8000)