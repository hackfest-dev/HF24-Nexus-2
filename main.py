from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func, update

from Database import models
from Database.sql import engine, SessionLocal

import httpx
# from Database.schema import CabBase, CabsResponse, DriversResponse, DriverBase, DeleteResponse, SearchRequest

# from Database.validation import validateDriver, validateCab, validateEmail

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Hack Crypto Api")

origins = [
    "*",
    "http://localhost:8000",
    "http://localhost:5174",
    "http://localhost:5173"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/users/{uid}", tags=["User"])
def get_user(uid: str,  db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.uid == uid).first()

    return user

@app.get("/get_users", tags=["Admin"])
def get_users(db: Session = Depends(get_db)):
    users = db.query(models.User).all()

    return users

@app.post("/create_user", tags=["User"])
def create_user(uid: str, First_Name:str, Last_Name: str, Email: str, Phone: str,  db: Session = Depends(get_db)):
    user_object = models.User(uid = uid, First_Name=First_Name, Last_Name = Last_Name, Email = Email)

    if(Phone):
        user_object.Phone = Phone

    user_object.Current_Balance = 0

    user_object.Account_Status = 1

    try:
        db.add(user_object)
        db.commit()
    except SQLAlchemyError as e:
        print("Error creating user:", str(e))
        raise HTTPException(status_code=500, detail="Error creating user")

    return user_object

@app.post("/add_balance", tags=["User"])
def add_balance(uid: str, quantity : str,  db: Session = Depends(get_db)):
    
    user_obj = db.query(models.User).filter_by(uid=uid).first()

    user_obj.Current_Balance += float(quantity)

    transaction = models.AccountTransactions(user_id = uid, transaction_type = "Deposit", quantity=quantity)

    try:
        db.add(transaction)
        db.commit()
    except SQLAlchemyError as e:
        print("Error during deposit:", str(e))
        raise HTTPException(status_code=500, detail="Error during deposit")

    return {"status": "Success"}

@app.get("/users/{uid}/crypto_transactions_info", tags=["Admin"])
def get_crypto_transactions_info(uid: str, db: Session = Depends(get_db)):
    transactions = db.query(models.CryptoTransactions).filter(models.CryptoTransactions.user_id == uid).all()

    transaction_info = []
    for transaction in transactions:
        transaction_data = {
            "Cryptocurrency Name": transaction.token_name,
            "Transaction Type": transaction.transaction_type,
            "Average Buying Price": None,
            "Date": transaction.transaction_time.strftime("%Y-%m-%d %H:%M:%S"),
            "Quantity": transaction.quantity,
            "Price": transaction.token_price,
            "Amount": transaction.quantity * transaction.token_price,
            "Realized P/L": None,
            "Realized P/L (%)": None
        }

        # Calculate moving average buying price
        moving_average_price_query = db.query(func.sum(models.CryptoTransactions.token_price * models.CryptoTransactions.quantity) / func.sum(models.CryptoTransactions.quantity)).filter(
            models.CryptoTransactions.user_id == uid,
            models.CryptoTransactions.token_name == transaction.token_name,
            models.CryptoTransactions.transaction_type == "BUY",
            models.CryptoTransactions.transaction_time <= transaction.transaction_time
        ).first()
        
        if moving_average_price_query[0] is not None:
            transaction_data["Average Buying Price"] = moving_average_price_query[0]

        # Check if there is a corresponding sell transaction
        sell_transaction = db.query(models.CryptoTransactions).filter(
            models.CryptoTransactions.user_id == uid,
            models.CryptoTransactions.token_name == transaction.token_name,
            models.CryptoTransactions.transaction_type == "SELL",
            models.CryptoTransactions.transaction_time == transaction.transaction_time
        ).first()

        if sell_transaction:
            # transaction_data["Sell Date"] = sell_transaction.transaction_time.strftime("%Y-%m-%d %H:%M:%S")
            # transaction_data["Sell Quantity"] = sell_transaction.quantity
            # transaction_data["Sell Price"] = sell_transaction.token_price
            # transaction_data["Sell Amount"] = sell_transaction.quantity * sell_transaction.token_price

            buy_amount = moving_average_price_query[0]*sell_transaction.quantity if moving_average_price_query else 0
            sell_amount = sell_transaction.quantity * sell_transaction.token_price
            realized_pl = sell_amount - buy_amount
            realized_pl_percentage = (float(realized_pl) / float(buy_amount)) * 100 if buy_amount != 0 else 0

            transaction_data["Realized P/L"] = realized_pl
            transaction_data["Realized P/L (%)"] = round(realized_pl_percentage, 6)

        transaction_info.append(transaction_data)

    return transaction_info

@app.post("/withdraw_money", tags=["User"])
def withdraw_money(uid: str, quantity : str,  db: Session = Depends(get_db)):
    
    user_obj = db.query(models.User).filter_by(uid=uid).first()

    if(user_obj.Current_Balance >= float(quantity)):
        user_obj.Current_Balance -= float(quantity)
    else:
        return {"status" : "Failure", "message" : "Not enough funds to withdraw"}

    transaction = models.AccountTransactions(user_id = uid, transaction_type = "Withdrawal", quantity=quantity)

    try:
        db.add(transaction)
        db.commit()
    except SQLAlchemyError as e:
        print("Error during withdrawal:", str(e))
        raise HTTPException(status_code=500, detail="Error during withdrawal")

    return {"status": "Success"}

@app.get("/users/{uid}/fetch_balance", tags=["User"])
def get_user(uid: str,  db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.uid == uid).first()

    if user:
        return {"user_id": uid, "balance": user.Current_Balance}
    else:
        raise HTTPException(status_code=404, detail=f"User with ID {uid} not found")
    
@app.post("/users/{uid}/buy_crypto", tags=["Crypto"])
async def buy_crypto(uid: str, token_id: str, quantity: float, db: Session = Depends(get_db)):
    # Check if the cryptocurrency data is already in the database
    coin_data = db.query(models.Crypto_Prices).filter(models.Crypto_Prices.token_id == token_id).first()

    if coin_data:
        fiat_price = float(coin_data.token_price) * quantity
    else:
        # Fetch coin data from CoinRanking API
        fetch_coin_data = f"https://coinranking1.p.rapidapi.com/coin/{token_id}"
        headers = {
            "X-RapidAPI-Key": "6c15ef80a9msh0fab964ed355602p120ff5jsn278d01eb24fb",
            "X-RapidAPI-Host": "coinranking1.p.rapidapi.com",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(fetch_coin_data, headers=headers)

        if response.status_code == 200:
            data = response.json()["data"]["coin"]
            fiat_price = float(data["price"]) * quantity

            # Create or update coin_data in the database
            coin_data = models.Crypto_Prices(
                token_id=data["uuid"],
                token_name=data["name"],
                token_symbol=data["symbol"],
                token_price=float(data["price"]),
            )
            db.add(coin_data)
            db.commit()
        else:
            raise HTTPException(status_code=500, detail="Failed to fetch cryptocurrency data from API")

    # Check user's balance
    user_obj = db.query(models.User).filter(models.User.uid == uid).first()
    if user_obj.Current_Balance < fiat_price:
        raise HTTPException(status_code=400, detail="Not enough balance to buy cryptocurrency")

    # Deduct fiat balance from user
    user_obj.Current_Balance -= fiat_price

    # Update or create crypto holding for the user
    user_holding = db.query(models.CryptoHoldings).filter(models.CryptoHoldings.user_id == uid).filter(models.CryptoHoldings.token_id == token_id).first()
    if user_holding is None:
        holding_obj = models.CryptoHoldings(user_id=uid, token_id=token_id, token_name=coin_data.token_name, token_symbol=coin_data.token_symbol, quantity=quantity)
    else:
        user_holding.quantity += quantity

    # Record transaction
    transaction = models.CryptoTransactions(
        user_id=uid,
        transaction_type="BUY",
        token_id=token_id,
        token_name=coin_data.token_name,
        token_symbol=coin_data.token_symbol,
        token_price=coin_data.token_price,
        quantity=quantity,
    )

    try:
        db.add(transaction)
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Error processing transaction")

    return {"status": "Success"}




@app.get("/fetch_coin_data")
async def fetch_coin_data(db: Session = Depends(get_db)):
    fetch_coin_data = "https://coinranking1.p.rapidapi.com/coins"

    headers = {
        "X-RapidAPI-Key": "6c15ef80a9msh0fab964ed355602p120ff5jsn278d01eb24fb",
        "X-RapidAPI-Host": "coinranking1.p.rapidapi.com",
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(fetch_coin_data, headers=headers)

    if response.status_code == 200:
        data = response.json()
        coins = data["data"]["coins"]

        for coin in coins:
            coin_data = models.Crypto_Prices(
                token_id=coin["uuid"],
                token_name=coin["name"],
                token_symbol=coin["symbol"],
                token_price=float(coin["price"]),
            )

            db.add(coin_data)
        db.commit()

    return {"status": "Success"}

@app.post("/users/{uid}/sell_crypto", tags=["Crypto"])
async def sell_crypto(uid: str, token_id: str, quantity: float, db: Session = Depends(get_db)):
    user_holding = db.query(models.CryptoHoldings).filter(models.CryptoHoldings.user_id == uid).filter(models.CryptoHoldings.token_id == token_id).first()
    holding_quantity = user_holding.quantity

    if holding_quantity >= quantity:
        user_holding.quantity -= quantity

        coin_data = db.query(models.Crypto_Prices).filter(models.Crypto_Prices.token_id == token_id).first()

        if coin_data:
            fiat_cash = float(coin_data.token_price) * quantity
        else:
            # Fetch coin data from CoinRanking API and store it in the table
            fetch_coin_data = f"https://coinranking1.p.rapidapi.com/coin/{token_id}"
            headers = {
                "X-RapidAPI-Key": "6c15ef80a9msh0fab964ed355602p120ff5jsn278d01eb24fb",
                "X-RapidAPI-Host": "coinranking1.p.rapidapi.com",
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(fetch_coin_data, headers=headers)

            if response.status_code == 200:
                data = response.json()
                data = data["data"]["coin"]
                fiat_cash = float(data["price"]) * quantity

                coin_data = models.Crypto_Prices(
                    token_id=data["uuid"],
                    token_name=data["name"],
                    token_symbol=data["symbol"],
                    token_price=float(data["price"]),
                )
                db.add(coin_data)
                db.commit()
            else:
                return {"status": "Failed"}

        user_obj = db.query(models.User).filter(models.User.uid == uid).first()
        user_obj.Current_Balance += fiat_cash

        transaction = models.CryptoTransactions(
            user_id=uid,
            transaction_type="SELL",
            token_id=token_id,
            token_name=coin_data.token_name,
            token_symbol=coin_data.token_symbol,
            token_price=coin_data.token_price,
            quantity=quantity,
        )

        try:
            db.add(transaction)
            db.commit()
        except SQLAlchemyError as e:
            print("Error during selling:", str(e))
            raise HTTPException(status_code=404, detail="Error during selling")

        return {"status": "Success"}
    else:
        return {"status": "Failed", "Reason": "Not enough holdings"}

@app.get("/users/{uid}/crypto_holdings", tags=["Crypto"])
def get_crypto_holdings(uid:str,  db: Session = Depends(get_db)):
    holdings = db.query(models.CryptoHoldings).filter(models.CryptoHoldings.user_id == uid).filter(models.CryptoHoldings.quantity != 0).order_by(models.CryptoHoldings.bought_at.desc()).all()

    return holdings

@app.get("/users/{uid}/crypto_transactions", tags=["Crypto"])
def crypto_transactions(uid:str,  db: Session = Depends(get_db)):
    holdings = db.query(models.CryptoTransactions).filter(models.CryptoTransactions.user_id == uid).order_by(models.CryptoTransactions.transaction_time.desc()).all()

    return holdings

@app.get("/users/{uid}/fiat_transactions", tags=["Crypto"])
def fiat_transactions(uid:str,  db: Session = Depends(get_db)):
    holdings = db.query(models.AccountTransactions).filter(models.AccountTransactions.user_id == uid).order_by(models.AccountTransactions.transaction_time.desc()).all()

    return holdings

@app.get("/users/{uid}/get_crypto_holding", tags=["Crypto"])
def get_crypto_holding(uid:str, token_id:str,  db: Session = Depends(get_db)):
    holdings = db.query(models.CryptoHoldings).filter(models.CryptoHoldings.user_id == uid).filter(models.CryptoHoldings.token_id == token_id).filter(models.CryptoHoldings.quantity != 0).order_by(models.CryptoHoldings.bought_at.desc()).first()

    if holdings is None:
        return {"status" : "Token not available", "quantity" : 0}
    
    return holdings

@app.get("/users/{uid}/initial_portfolio_value", tags=["Crypto"])
def initial_portfolio_value(uid:str,  db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.uid == uid).first()
    transactions = user.transactions_crypto

    original_value = 0.0

    for transaction in transactions:
        if transaction.transaction_type == "SELL":
            original_value -= transaction.token_price * transaction.quantity
        else:
            original_value += transaction.token_price * transaction.quantity

    return { "original_value" : original_value }

