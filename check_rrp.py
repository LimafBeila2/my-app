import asyncio
from curl_cffi.requests import AsyncSession

# --- ТВОИ ДАННЫЕ (Впиши их здесь) ---
TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJob0tTcHBhQjR0QnpMbjdWTzYyNGtlQldnbFBJaDZpaUNGNmhjYVduRGZrIn0.eyJleHAiOjE3NzY1NTQ1NTgsImlhdCI6MTc3NjU1Mjc1OCwianRpIjoiZTg1ZDBiMDQtMTg2OC00ZDMyLTkxZmQtZDE1NWMyMGVhNTZjIiwiaXNzIjoiaHR0cDovL2tleWNsb2FrLmRlZmF1bHQuc3ZjLmNsdXN0ZXIubG9jYWwvcmVhbG1zL21hc3RlciIsImF1ZCI6ImFjY291bnQiLCJzdWIiOiJjNzVmNzkxNS0zMjk5LTRjOTItOWM1Yy04M2RlNTU3MWQzMWYiLCJ0eXAiOiJCZWFyZXIiLCJhenAiOiJjdXN0b21lci1hcHAiLCJzZXNzaW9uX3N0YXRlIjoiMzk3MmM3YTctYjYzZi00OTRkLWIwOTctOWZlZmVlNjRmOWIzIiwicmVhbG1fYWNjZXNzIjp7InJvbGVzIjpbImRlZmF1bHQtcm9sZXMtbWFzdGVyIiwib2ZmbGluZV9hY2Nlc3MiLCJtcF9wYWNrZXIiLCJtcF9maW5hbmNpYWxfbWFuYWdlciIsInVtYV9hdXRob3JpemF0aW9uIiwibXBfY29udGVudF9tYW5hZ2VyIl19LCJyZXNvdXJjZV9hY2Nlc3MiOnsiYWNjb3VudCI6eyJyb2xlcyI6WyJtYW5hZ2UtYWNjb3VudCIsIm1hbmFnZS1hY2NvdW50LWxpbmtzIiwidmlldy1wcm9maWxlIl19fSwic2NvcGUiOiJvZmZsaW5lX2FjY2VzcyBlbWFpbCBwcm9maWxlIiwic2lkIjoiMzk3MmM3YTctYjYzZi00OTRkLWIwOTctOWZlZmVlNjRmOWIzIiwiZW1haWxfdmVyaWZpZWQiOmZhbHNlLCJuYW1lIjoixZ7EsFJYQU4gUcaPSFLGj01BTk9WIiwicHJlZmVycmVkX3VzZXJuYW1lIjoiOTk0NzcxMjI0NTc0LTEyMTcxIiwiZ2l2ZW5fbmFtZSI6IsWexLBSWEFOIiwiZmFtaWx5X25hbWUiOiJRxo9IUsaPTUFOT1YifQ.b7GoC--OGzWOkFhxgwme-2PGZpsFo_NFHn1XDq-vReGhMwUTnQ5rqPL4knlqXXK-LAZEtJRDjSGkkXbCiT5mR--7Q2UkqdVR-3UpC5h0iw70x-xI5AD_awooLS02ZGy1J298wWWUNHsO91izR4C7RLDwQJ6EBFdis5MkDCHTQ02TWvy8lW8AU4B8kT8p7_zATKJESwlchATDuMiDOfAL3A7AVL2AZyE6wGIgNL9AiIu0XGbx6-XlZEtej1ilyVhaqLRRp7xNABBNC9-LwTaWiAjj9VDBXcdBGjdd-apL5AzVI5BfNbwZxHet95AM4IexmAXVuSvGN9QrcMcBYJqr-g"
MERCHANT_UUID = "f6251c9e-f291-4634-b35e-62e38d20929e" # Твой Smart ProLine или SmartHouse
PRODUCT_ID = "1407660" # ID товара, который проверяем

async def get_rrp():
    # URL для получения данных конкретного товара из твоего кабинета
    url = f"https://api.umico.az/api/v1/merchant/products/{PRODUCT_ID}"
    
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/json"
    }

    async with AsyncSession(impersonate="chrome124") as session:
        try:
            response = await session.get(url, headers=headers)
            
            if response.status_code == 200:
                data = response.json().get('data', {})
                name = data.get('name_ru', 'Нет названия')
                rrp = data.get('retail_price', 'Не найдена')
                
                print(f"\n✅ ТОВАР: {name}")
                print(f"💰 RRP ЦЕНА: {rrp} AZN")
            
            elif response.status_code == 401:
                print("❌ ОШИБКА: Токен не подходит!")
            elif response.status_code == 404:
                print(f"❌ ОШИБКА: Товар {PRODUCT_ID} не найден в этом магазине")
            else:
                print(f"⚠️ ОШИБКА API: {response.status_code}")
                
        except Exception as e:
            print(f"⚠️ ОШИБКА: {e}")

if __name__ == "__main__":
    asyncio.run(get_rrp())